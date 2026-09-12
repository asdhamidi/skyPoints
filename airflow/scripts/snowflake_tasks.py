"""
SkyPoints Airflow task implementations — extracted from the DAG file so this
business logic (Snowflake connection handling, SQL construction, per-source
staging, the run summary) is independently testable without Airflow itself
being importable. See tests/test_snowflake_tasks.py.

airflow/dags/skypoints_daily_pipeline.py imports this module and wires these
functions into tasks; it contains no business logic of its own.
"""
from __future__ import annotations

import os

AUS_COLUMNS = ["unique_id", "member_name", "tier_type", "date_of_birth", "date_of_enrollment", "date_of_flight"]
IND_COLUMNS = ["id", "name", "dob", "tier_code", "enrollment_date", "individual_or_corporate", "flight_date"]
USA_COLUMNS = ["id", "name", "tier_code", "enrollment_date", "flight_date"]


def load_private_key(key_path: str, passphrase: str | None = None) -> bytes:
    """Loads a PEM private key and re-serializes it to the DER/PKCS8 bytes
    snowflake-connector-python's `private_key` parameter expects."""
    from cryptography.hazmat.primitives import serialization

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


def get_snowflake_connection(role: str = "SKYPOINTS_LOADER", warehouse: str = "LOAD_WH"):
    """role/warehouse are explicit per-call parameters, not read from
    SNOWFLAKE_ROLE/SNOWFLAKE_WAREHOUSE env vars — different tasks need
    different roles (LOADER for ingestion, TRANSFORMER for the summary query),
    and a single fixed env var can't express that."""
    import snowflake.connector

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=load_private_key(
            os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
            os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None,
        ),
        role=role,
        warehouse=warehouse,
        database=os.environ.get("SNOWFLAKE_DATABASE", "SKYPOINTS"),
        schema="RAW",
    )


def build_put_sql(local_path: str, stage: str) -> str:
    return f"PUT file://{local_path} @{stage} OVERWRITE = FALSE AUTO_COMPRESS = TRUE"


def build_copy_into_csv_sql(table: str, stage: str, columns: list[str], filename: str) -> str:
    select_list = ", ".join(f"${i + 1}" for i in range(len(columns))) + ", METADATA$FILENAME"
    column_list = ", ".join(columns) + ", source_file_name"
    return f"""
        COPY INTO {table} ({column_list})
        FROM (SELECT {select_list} FROM @{stage})
        PATTERN = '.*{filename}.*'
        FILE_FORMAT = (FORMAT_NAME = RAW.CSV_FORMAT)
        ON_ERROR = ABORT_STATEMENT
    """


def build_copy_into_json_sql(filename: str) -> str:
    return f"""
        COPY INTO RAW.REDEMPTION_FEED (payload, source_file_name)
        FROM (SELECT $1, METADATA$FILENAME FROM @RAW.REDEMPTION_STAGE)
        PATTERN = '.*{filename}.*'
        FILE_FORMAT = (FORMAT_NAME = RAW.JSON_FORMAT)
        ON_ERROR = ABORT_STATEMENT
    """


def put_and_copy_csv(cur, local_path: str, stage: str, table: str, columns: list[str]) -> None:
    """PUT a CSV to its stage, then COPY INTO its RAW table. Idempotent:
    COPY INTO skips a file name it has already loaded unless FORCE=TRUE
    (docs/03 §4 — 'Idempotency')."""
    filename = os.path.basename(local_path)
    cur.execute(build_put_sql(local_path, stage))
    cur.execute(build_copy_into_csv_sql(table, stage, columns, filename))


def member_file_path(landing_dir: str, source: str, run_date: str, ext: str) -> str:
    return f"{landing_dir}/{source}_member_{run_date}.{ext}"


def redemption_file_path(landing_dir: str, run_date: str) -> str:
    return f"{landing_dir}/redemption_{run_date}.json"


def convert_aus_xlsx(landing_dir: str, run_date: str) -> None:
    from convert_aus_xlsx_to_csv import convert

    xlsx_path = member_file_path(landing_dir, "aus", run_date, "xlsx")
    csv_path = member_file_path(landing_dir, "aus", run_date, "csv")
    convert(xlsx_path, csv_path)


def stage_and_copy_aus(landing_dir: str, run_date: str) -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        put_and_copy_csv(
            cur,
            member_file_path(landing_dir, "aus", run_date, "csv"),
            "RAW.MEMBER_PROFILE_STAGE",
            "RAW.AUS_MEMBER_PROFILE",
            AUS_COLUMNS,
        )
    finally:
        conn.close()


def stage_and_copy_ind(landing_dir: str, run_date: str) -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        put_and_copy_csv(
            cur,
            member_file_path(landing_dir, "ind", run_date, "csv"),
            "RAW.MEMBER_PROFILE_STAGE",
            "RAW.IND_MEMBER_PROFILE",
            IND_COLUMNS,
        )
    finally:
        conn.close()


def stage_and_copy_usa(landing_dir: str, run_date: str) -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        put_and_copy_csv(
            cur,
            member_file_path(landing_dir, "usa", run_date, "csv"),
            "RAW.MEMBER_PROFILE_STAGE",
            "RAW.USA_MEMBER_PROFILE",
            USA_COLUMNS,
        )
    finally:
        conn.close()


def stage_and_copy_redemptions(landing_dir: str, run_date: str) -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        local_path = redemption_file_path(landing_dir, run_date)
        filename = os.path.basename(local_path)
        cur.execute(build_put_sql(local_path, "RAW.REDEMPTION_STAGE"))
        cur.execute(build_copy_into_json_sql(filename))
    finally:
        conn.close()


def publish_run_summary() -> None:
    """Logs row counts per country table and redemption match_status counts —
    the cheap, queryable observability check that the run actually did
    something, not just that every task returned success."""
    conn = get_snowflake_connection(role="SKYPOINTS_TRANSFORMER", warehouse="TRANSFORM_WH")
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
