.PHONY: bootstrap up down

bootstrap:
	@echo "Run setup/snowflake_bootstrap.sql manually against your Snowflake account (as ACCOUNTADMIN),"
	@echo "then setup/verify_bootstrap.sql to confirm every object was created."

up:
	cd airflow && docker compose up -d

down:
	cd airflow && docker compose down
