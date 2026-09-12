.PHONY: bootstrap up down demo dbt-fast test

bootstrap:
	@echo "Run setup/snowflake_bootstrap.sql manually against your Snowflake account (as ACCOUNTADMIN),"
	@echo "then setup/verify_bootstrap.sql to confirm every object was created."

up:
	cd airflow && docker compose up -d --build

down:
	cd airflow && docker compose down

# make demo DATE=2024-01-15
demo:
ifndef DATE
	$(error DATE is required, e.g. make demo DATE=2024-01-15)
endif
	python demo/generate_sample_feed.py --run-date $(DATE) --out-dir landing
	@echo "Fixtures written to landing/ for $(DATE)."
	@echo "In the Airflow UI: unpause skypoints_daily_pipeline, then trigger it for logical date $(DATE)."

# Fast local dbt iteration against DuckDB - no Snowflake credits, no Docker.
dbt-fast:
	cd dbt && dbt build --target duckdb

test:
	pytest
