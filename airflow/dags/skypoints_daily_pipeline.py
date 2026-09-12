"""
SkyPoints daily pipeline — DAG wiring only. All task business logic lives in
airflow/scripts/snowflake_tasks.py, which is independently testable without
Airflow itself importable (see tests/test_snowflake_tasks.py). This file just
defines tasks and their dependencies.

Sequence (docs/03_Technical_Build_Plan.md §4): wait for the day's per-country
+ redemption files -> convert AUS's Excel to CSV -> stage+load the four RAW
tables -> dbt seed -> dbt snapshot -> dbt run (staging, then marts) -> dbt
test -> log a run summary.
"""
from __future__ import annotations

import sys
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.sensors.filesystem import FileSensor

sys.path.insert(0, "/opt/airflow/scripts")

import snowflake_tasks as tasks  # noqa: E402

LANDING_DIR = "/opt/airflow/landing"
DBT_PROJECT_DIR = "/opt/airflow/dbt_project"
DBT_BIN = "/opt/dbt_venv/bin/dbt"


def _convert_aus_xlsx(**context):
    tasks.convert_aus_xlsx(LANDING_DIR, context["ds_nodash"])


def _stage_and_copy_aus(**context):
    tasks.stage_and_copy_aus(LANDING_DIR, context["ds_nodash"])


def _stage_and_copy_ind(**context):
    tasks.stage_and_copy_ind(LANDING_DIR, context["ds_nodash"])


def _stage_and_copy_usa(**context):
    tasks.stage_and_copy_usa(LANDING_DIR, context["ds_nodash"])


def _stage_and_copy_redemptions(**context):
    tasks.stage_and_copy_redemptions(LANDING_DIR, context["ds_nodash"])


def _publish_run_summary(**context):
    tasks.publish_run_summary()


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
        python_callable=_convert_aus_xlsx,
    )
    stage_and_copy_aus_task = PythonOperator(
        task_id="stage_and_copy_aus",
        python_callable=_stage_and_copy_aus,
    )
    stage_and_copy_ind_task = PythonOperator(
        task_id="stage_and_copy_ind",
        python_callable=_stage_and_copy_ind,
    )
    stage_and_copy_usa_task = PythonOperator(
        task_id="stage_and_copy_usa",
        python_callable=_stage_and_copy_usa,
    )
    stage_and_copy_redemptions_task = PythonOperator(
        task_id="stage_and_copy_redemptions",
        python_callable=_stage_and_copy_redemptions,
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
        python_callable=_publish_run_summary,
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
    ] >> dbt_seed >> dbt_run_staging >> dbt_snapshot >> dbt_run_marts >> dbt_test >> publish_run_summary_task
