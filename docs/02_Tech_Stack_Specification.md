# SkyPoints — Platform & Tooling Specification

Defines the platform stack, environment topology, and operational configuration the SkyPoints pipeline runs on.

---

## 1. Platform Summary

| Layer | Technology | Role |
|---|---|---|
| Warehouse | Snowflake | Storage and compute for raw, staging, and marts data |
| Transformation & testing | dbt (`dbt-snowflake` adapter; `dbt-duckdb` for local dev only) | Models, snapshots, seeds, schema/singular tests |
| Orchestration | Apache Airflow, `LocalExecutor` | Scheduling, file sensing, task sequencing, retries |
| Packaging | Docker Compose | Reproducible local Airflow deployment |
| CI | GitHub Actions | `dbt build`/`dbt test` against the DuckDB target, DAG-integrity check |

---

## 2. Snowflake Environment

```sql
CREATE DATABASE IF NOT EXISTS SKYPOINTS;
CREATE SCHEMA IF NOT EXISTS SKYPOINTS.RAW;
CREATE SCHEMA IF NOT EXISTS SKYPOINTS.STAGING;
CREATE SCHEMA IF NOT EXISTS SKYPOINTS.MARTS;

CREATE WAREHOUSE IF NOT EXISTS LOAD_WH      WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE;
CREATE WAREHOUSE IF NOT EXISTS TRANSFORM_WH WAREHOUSE_SIZE = 'SMALL'  AUTO_SUSPEND = 60 AUTO_RESUME = TRUE;

CREATE ROLE IF NOT EXISTS SKYPOINTS_LOADER;       -- USAGE+INSERT on RAW, USAGE on LOAD_WH
CREATE ROLE IF NOT EXISTS SKYPOINTS_TRANSFORMER;  -- USAGE on all schemas, USAGE on TRANSFORM_WH

CREATE FILE FORMAT IF NOT EXISTS SKYPOINTS.RAW.CSV_FORMAT  TYPE = CSV SKIP_HEADER = 1 NULL_IF = ('', 'NULL') ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE;
CREATE FILE FORMAT IF NOT EXISTS SKYPOINTS.RAW.JSON_FORMAT TYPE = JSON;

CREATE STAGE IF NOT EXISTS SKYPOINTS.RAW.MEMBER_PROFILE_STAGE FILE_FORMAT = SKYPOINTS.RAW.CSV_FORMAT;
CREATE STAGE IF NOT EXISTS SKYPOINTS.RAW.REDEMPTION_STAGE     FILE_FORMAT = SKYPOINTS.RAW.JSON_FORMAT;

CREATE RESOURCE MONITOR IF NOT EXISTS SKYPOINTS_MONITOR
  WITH CREDIT_QUOTA = 25 TRIGGERS ON 80 PERCENT DO NOTIFY ON 100 PERCENT DO SUSPEND;
ALTER WAREHOUSE LOAD_WH      SET RESOURCE_MONITOR = SKYPOINTS_MONITOR;
ALTER WAREHOUSE TRANSFORM_WH SET RESOURCE_MONITOR = SKYPOINTS_MONITOR;

CREATE USER IF NOT EXISTS SKYPOINTS_DBT
  DEFAULT_ROLE = SKYPOINTS_TRANSFORMER
  DEFAULT_WAREHOUSE = TRANSFORM_WH
  DEFAULT_NAMESPACE = SKYPOINTS.STAGING
  COMMENT = 'Service account used by both Airflow ingestion and dbt transformations';
GRANT ROLE SKYPOINTS_TRANSFORMER TO USER SKYPOINTS_DBT;
GRANT ROLE SKYPOINTS_LOADER TO USER SKYPOINTS_DBT;
```

`SKYPOINTS_DBT` is the single service account used both by Airflow's ingestion tasks (connecting as `SKYPOINTS_LOADER`) and by dbt's `snowflake` target (`SNOWFLAKE_USER` in `dbt/profiles/profiles.yml.example`, as `SKYPOINTS_TRANSFORMER`) — one credential set in `.env`, each caller picks its role explicitly per connection rather than relying on the user's default role. Full statement with password handling: `setup/snowflake_bootstrap.sql` §8.

Snowflake has no native Excel file format. `AUS.xlsx` is converted to CSV by a pipeline component (`airflow/scripts/convert_aus_xlsx_to_csv.py`) before it reaches `MEMBER_PROFILE_STAGE`; `IND.csv`/`USA.csv` are staged directly.

Stage type: Snowflake internal named stage. No external cloud storage account is provisioned — every source in this build is a local file (§4), so `PUT` to an internal stage is sufficient; a production Source System delivering to cloud object storage would substitute an external stage + Snowpipe without changing anything downstream of `COPY INTO`.

---

## 3. dbt

- Adapter: `dbt-snowflake` (production/demo target), `dbt-duckdb` (local development target only — never used for the live demo or CI's authority on Snowflake behavior).
- Packages: `dbt_utils`, `dbt_expectations`.
- Two profiles in `profiles.yml`: `snowflake` (used by Airflow and the live demo) and `duckdb` (used by `make dbt-fast`).
- Project layout, models, snapshots, macros, seeds, and tests are specified in `03_Technical_Build_Plan.md`.

---

## 4. Airflow

- Executor: `LocalExecutor` — single-node, no distributed workers required for this pipeline's volume.
- `dbt` runs from an isolated Python virtualenv (`/opt/dbt_venv`) baked into the Airflow image at build time, invoked via `BashOperator`. This keeps `dbt-snowflake`'s dependency set separate from Airflow's own, avoiding version conflicts between the two. `dbt deps` runs once, in `airflow-init`, against the bind-mounted `dbt/` project — not at image-build time, since the project isn't present in the build context under the bind-mount approach.
- Snowflake access from the DAG's ingestion tasks uses `snowflake-connector-python` directly (`PythonOperator`), reading the same plain `SNOWFLAKE_*` environment variables dbt's `profiles.yml` already uses — not an Airflow Connection object or `apache-airflow-providers-snowflake`. One fewer dependency in the Airflow image, and no connection-URI to construct/encode (a real risk if the password contains URI-reserved characters).
- Schedule: `@daily`, `catchup=False`, `max_active_runs=1`, `retries=1`.
- Full DAG/task specification is in `03_Technical_Build_Plan.md`.

---

## 5. Local Development Environment

- `make dbt-fast` runs `dbt build --target duckdb` against locally generated fixtures — no Snowflake credits consumed, no network dependency.
- `make up` / `make down` bring the Airflow stack up/down via `docker-compose`.
- `make bootstrap` runs the one-time Snowflake environment script (§2) against the target account.

---

## 6. CI/CD

`.github/workflows/ci.yml` runs on every push:
1. `dbt build --target duckdb`
2. `dbt test --target duckdb`
3. A `pytest` check that the Airflow DAG parses (`DagBag`) with no import errors or cycles.

CI never connects to Snowflake and requires no cloud credentials — safe for a public repository. The Snowflake path is exercised in the live demo (`03_Technical_Build_Plan.md` §6), not in CI.

---

## 7. Secrets and Configuration

- `.env` (git-ignored) holds `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`, `AIRFLOW_UID`.
- `.env.example` is committed as a template with no real values.
- Airflow's `skypoints_snowflake` connection is created from these environment variables at container startup — never hardcoded in DAG code or dbt profiles.
- Authentication: username/password for this build. Key-pair authentication is the recommended production hardening, not implemented here.

---

## 8. Dependency Versions

| Package | Version | Scope |
|---|---|---|
| `apache-airflow` | 2.9.x | installed from the official Airflow image's constraints file |
| `dbt-snowflake` | 1.8.x | isolated venv inside the Airflow image |
| `dbt-duckdb` | 1.8.x | local dev only, not shipped in the Airflow image |
| `apache-airflow-providers-snowflake` | latest compatible with 2.9.x | Airflow image |
| Python | 3.11 | Airflow image and local dev |
