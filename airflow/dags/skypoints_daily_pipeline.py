"""
SkyPoints daily pipeline.

Sequence (docs/03_Technical_Build_Plan.md §4): wait for the day's per-country
+ redemption files -> convert AUS's Excel to CSV -> stage+load the four RAW
tables -> dbt seed -> dbt snapshot -> dbt run (staging, then marts) -> dbt
test -> log a run summary.

Snowflake access uses snowflake-connector-python directly, reading the same
plain SNOWFLAKE_* environment variables dbt's profiles.yml already uses — not
an Airflow Connection object (docs/02_Tech_Stack_Specification.md §4).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.sensors.filesystem import FileSensor

sys.path.insert(0, "/opt/airflow/scripts")

LANDING_DIR = "/opt/airflow/landing"
DBT_PROJECT_DIR = "/opt/airflow/dbt_project"
DBT_BIN = "/opt/dbt_venv/bin/dbt"


def _load_private_key() -> bytes:
    """Key-pair auth, not a password — see setup/snowflake_bootstrap.sql §8
    for why. Loads the PEM private key and re-serializes it to the DER/PKCS8
    bytes snowflake-connector-python's `private_key` parameter expects."""
    from cryptography.hazmat.primitives import serialization

    key_path = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
    passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    with open(key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=passphrase.encode() if passphrase else None,
        )
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _snowflake_connection(role: str = "SKYPOINTS_LOADER", warehouse: str = "LOAD_WH"):
    """role/warehouse are explicit per-call parameters, not read from
    SNOWFLAKE_ROLE/SNOWFLAKE_WAREHOUSE env vars — different tasks need
    different roles (LOADER for ingestion, TRANSFORMER for the summary query),
    and a single fixed env var can't express that."""
    import snowflake.connector

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=_load_private_key(),
        role=role,
        warehouse=warehouse,
        database=os.environ.get("SNOWFLAKE_DATABASE", "SKYPOINTS"),
        schema="RAW",
    )


def _put_and_copy_csv(cur, local_path: str, stage: str, table: str, columns: list[str]) -> None:
    """PUT a CSV to its stage, then COPY INTO its RAW table. Idempotent:
    COPY INTO skips a file name it has already loaded unless FORCE=TRUE
    (docs/03 §4 — 'Idempotency'). Column order here must match both the
    fixture generator's header order and the RAW table's DDL — see
    setup/raw_tables.sql and demo/generate_sample_feed.py."""
    filename = os.path.basename(local_path)
    cur.execute(f"PUT file://{local_path} @{stage} OVERWRITE = FALSE AUTO_COMPRESS = TRUE")
    select_list = ", ".join(f"${i + 1}" for i in range(len(columns)))
    column_list = ", ".join(columns) + ", source_file_name"
    cur.execute(f"""
        COPY INTO {table} ({column_list})
        FROM (SELECT {select_list}, METADATA$FILENAME FROM @{stage})
        PATTERN = '.*{filename}.*'
        FILE_FORMAT = (FORMAT_NAME = RAW.CSV_FORMAT)
        ON_ERROR = ABORT_STATEMENT
    """)


def convert_aus_xlsx(**context):
    from convert_aus_xlsx_to_csv import convert

    run_date = context["ds_nodash"]
    xlsx_path = f"{LANDING_DIR}/aus_member_{run_date}.xlsx"
    csv_path = f"{LANDING_DIR}/aus_member_{run_date}.csv"
    convert(xlsx_path, csv_path)


def stage_and_copy_aus(**context):
    run_date = context["ds_nodash"]
    conn = _snowflake_connection()
    try:
        cur = conn.cursor()
        _put_and_copy_csv(
            cur,
            f"{LANDING_DIR}/aus_member_{run_date}.csv",
            "RAW.MEMBER_PROFILE_STAGE",
            "RAW.AUS_MEMBER_PROFILE",
            ["unique_id", "member_name", "tier_type", "date_of_birth", "date_of_enrollment", "date_of_flight"],
        )
    finally:
        conn.close()


def stage_and_copy_ind(**context):
    run_date = context["ds_nodash"]
    conn = _snowflake_connection()
    try:
        cur = conn.cursor()
        _put_and_copy_csv(
            cur,
            f"{LANDING_DIR}/ind_member_{run_date}.csv",
            "RAW.MEMBER_PROFILE_STAGE",
            "RAW.IND_MEMBER_PROFILE",
            ["id", "name", "dob", "tier_code", "enrollment_date", "individual_or_corporate", "flight_date"],
        )
    finally:
        conn.close()


def stage_and_copy_usa(**context):
    run_date = context["ds_nodash"]
    conn = _snowflake_connection()
    try:
        cur = conn.cursor()
        _put_and_copy_csv(
            cur,
            f"{LANDING_DIR}/usa_member_{run_date}.csv",
            "RAW.MEMBER_PROFILE_STAGE",
            "RAW.USA_MEMBER_PROFILE",
            ["id", "name", "tier_code", "enrollment_date", "flight_date"],
        )
    finally:
        conn.close()


def stage_and_copy_redemptions(**context):
    run_date = context["ds_nodash"]
    filename = f"redemption_{run_date}.json"
    conn = _snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"PUT file://{LANDING_DIR}/{filename} @RAW.REDEMPTION_STAGE "
            "OVERWRITE = FALSE AUTO_COMPRESS = TRUE"
        )
        cur.execute(f"""
            COPY INTO RAW.REDEMPTION_FEED (payload, source_file_name)
            FROM (SELECT $1, METADATA$FILENAME FROM @RAW.REDEMPTION_STAGE)
            PATTERN = '.*{filename}.*'
            FILE_FORMAT = (FORMAT_NAME = RAW.JSON_FORMAT)
            ON_ERROR = ABORT_STATEMENT
        """)
    finally:
        conn.close()


def publish_run_summary(**context):
    """Logs row counts per country table and redemption match_status counts —
    the cheap, queryable observability check that the run actually did
    something, not just that every task returned success."""
    conn = _snowflake_connection(role="SKYPOINTS_TRANSFORMER", warehouse="TRANSFORM_WH")
    try:
        cur = conn.cursor()
        cur.execute("SELECT country_code FROM SKYPOINTS.STAGING.country_reference")
        for (country,) in cur.fetchall():
            cur.execute(f"SELECT COUNT(*) FROM SKYPOINTS.MARTS.TABLE_{country}")
            print(f"MARTS.TABLE_{country}: {cur.fetchone()[0]} rows")

        cur.execute(
            "SELECT match_status, COUNT(*) FROM SKYPOINTS.MARTS.REDEMPTIONS GROUP BY match_status"
        )
        for status, count in cur.fetchall():
            print(f"redemptions.match_status={status}: {count}")
    finally:
        conn.close()


default_args = {
    "retries": 1,
}

with DAG(
    dag_id="skypoints_daily_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
) as dag:

    check_aus_file = FileSensor(
        task_id="check_aus_file",
        filepath=LANDING_DIR + "/aus_member_{{ ds_nodash }}.xlsx",
        poke_interval=30,
        timeout=60 * 60,
        mode="reschedule",
    )
    check_ind_file = FileSensor(
        task_id="check_ind_file",
        filepath=LANDING_DIR + "/ind_member_{{ ds_nodash }}.csv",
        poke_interval=30,
        timeout=60 * 60,
        mode="reschedule",
    )
    check_usa_file = FileSensor(
        task_id="check_usa_file",
        filepath=LANDING_DIR + "/usa_member_{{ ds_nodash }}.csv",
        poke_interval=30,
        timeout=60 * 60,
        mode="reschedule",
    )
    check_redemption_file = FileSensor(
        task_id="check_redemption_file",
        filepath=LANDING_DIR + "/redemption_{{ ds_nodash }}.json",
        poke_interval=30,
        timeout=60 * 60,
        mode="reschedule",
    )

    convert_aus_xlsx_task = PythonOperator(
        task_id="convert_aus_xlsx",
        python_callable=convert_aus_xlsx,
    )

    stage_and_copy_aus_task = PythonOperator(
        task_id="stage_and_copy_aus",
        python_callable=stage_and_copy_aus,
    )
    stage_and_copy_ind_task = PythonOperator(
        task_id="stage_and_copy_ind",
        python_callable=stage_and_copy_ind,
    )
    stage_and_copy_usa_task = PythonOperator(
        task_id="stage_and_copy_usa",
        python_callable=stage_and_copy_usa,
    )
    stage_and_copy_redemptions_task = PythonOperator(
        task_id="stage_and_copy_redemptions",
        python_callable=stage_and_copy_redemptions,
    )

    dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"cd {DBT_PROJECT_DIR} && {DBT_BIN} seed --target snowflake",
    )
    dbt_snapshot = BashOperator(
        task_id="dbt_snapshot",
        bash_command=f"cd {DBT_PROJECT_DIR} && {DBT_BIN} snapshot --target snowflake",
    )
    dbt_run_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"cd {DBT_PROJECT_DIR} && {DBT_BIN} run --target snowflake --select staging",
    )
    dbt_run_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=f"cd {DBT_PROJECT_DIR} && {DBT_BIN} run --target snowflake --select marts",
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_PROJECT_DIR} && {DBT_BIN} test --target snowflake",
    )

    publish_run_summary_task = PythonOperator(
        task_id="publish_run_summary",
        python_callable=publish_run_summary,
    )

    check_aus_file >> convert_aus_xlsx_task >> stage_and_copy_aus_task
    check_ind_file >> stage_and_copy_ind_task
    check_usa_file >> stage_and_copy_usa_task
    check_redemption_file >> stage_and_copy_redemptions_task

    [
        stage_and_copy_aus_task,
        stage_and_copy_ind_task,
        stage_and_copy_usa_task,
        stage_and_copy_redemptions_task,
    ] >> dbt_seed >> dbt_snapshot >> dbt_run_staging >> dbt_run_marts >> dbt_test >> publish_run_summary_task
