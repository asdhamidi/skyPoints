# SkyPoints Airflow image. dbt is deliberately NOT installed into this image's
# main Python environment — see docs/02_Tech_Stack_Specification.md §4: dbt's
# dependency set has a real history of conflicting with Airflow's own pinned
# dependencies. It lives in an isolated venv instead, invoked via BashOperator.

FROM apache/airflow:2.9.3-python3.11

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

RUN python -m venv /opt/dbt_venv \
    && /opt/dbt_venv/bin/pip install --no-cache-dir dbt-snowflake==1.8.4
