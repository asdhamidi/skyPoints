FROM apache/airflow:2.9.3-python3.11

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

USER root

RUN python -m venv /opt/dbt_venv \
    && chown -R airflow: /opt/dbt_venv

USER airflow

RUN /opt/dbt_venv/bin/pip install --no-cache-dir dbt-snowflake==1.8.4
RUN /opt/dbt_venv/bin/pip install --no-cache-dir openpyxl