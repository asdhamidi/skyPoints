# SkyPoints — Build Blueprint

Component-level blueprint of everything to be built. Implements the data contract in `01_Design_Specification.md` on the platform defined in `02_Tech_Stack_Specification.md`.

---

## 1. System Architecture

```
 landing/aus_member_<date>.xlsx ─┐
 landing/ind_member_<date>.csv ──┼──► FileSensor tasks (Airflow)
 landing/usa_member_<date>.csv ──┘
 landing/redemption_<date>.json ─────► FileSensor task (Airflow)
                                          │
                                          ▼
                         convert_aus_xlsx_to_csv.py
                                          │
                                          ▼
                    PUT + COPY INTO  (per-source, Snowflake)
                                          │
                                          ▼
     RAW.AUS_MEMBER_PROFILE / IND_MEMBER_PROFILE / USA_MEMBER_PROFILE / REDEMPTION_FEED
                                          │
                                          ▼
                              dbt seed  (country_reference, tier_reference)
                                          ▼
              stg_member_profile_aus / _ind / _usa  ──► UNION ──► stg_member_profile
                                          ▼
                         dbt snapshot: snap_member_country  (SCD2 on tracked attributes)
                                          ▼
                              int_member_profile_final
                                          ▼
                 generate_country_tables macro  ──►  MARTS.TABLE_AUS / TABLE_IND / TABLE_USA / …
                                          │
     stg_redemptions (LATERAL FLATTEN) ──► marts.redemptions (joined to int_member_profile_final)
                                          ▼
                                     dbt test
                                          ▼
                              publish_run_summary
```

---

## 2. Repository Layout

```
skyPoints/
├── README.md
├── docs/
│   ├── 01_Design_Specification.md
│   ├── 02_Tech_Stack_Specification.md
│   └── 03_Technical_Build_Plan.md
├── SkyPoints_Engineering_Practices.md
├── SkyPoints_Source_Data_Findings.md
├── setup/
│   └── snowflake_bootstrap.sql
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
├── tests/
│   ├── test_generate_sample_feed.py
│   ├── test_convert_aus_xlsx_to_csv.py
│   └── test_snowflake_tasks.py
├── demo/
│   ├── generate_sample_feed.py
│   └── DEMO_RUNBOOK.md
├── dbt/
│   ├── dbt_project.yml
│   ├── packages.yml
│   ├── profiles/profiles.yml.example
│   ├── seeds/
│   │   ├── country_reference.csv
│   │   └── tier_reference.csv
│   ├── models/
│   │   ├── staging/
│   │   │   ├── _staging__sources.yml
│   │   │   ├── _staging__models.yml
│   │   │   ├── stg_member_profile_aus.sql
│   │   │   ├── stg_member_profile_ind.sql
│   │   │   ├── stg_member_profile_usa.sql
│   │   │   ├── stg_member_profile.sql
│   │   │   └── stg_redemptions.sql
│   │   └── marts/
│   │       ├── _marts__models.yml
│   │       ├── int_member_profile_final.sql
│   │       ├── generate_country_tables.sql
│   │       └── redemptions.sql
│   ├── snapshots/
│   │   └── snap_member_country.sql
│   ├── macros/
│   │   ├── generate_country_tables.sql
│   │   ├── calculate_age.sql
│   │   ├── is_stale_member.sql
│   │   ├── extract_feed_date.sql
│   │   └── parse_usa_date.sql
│   └── tests/singular/
│       ├── assert_member_key_unique.sql
│       ├── assert_country_code_is_valid.sql
│       ├── assert_no_duplicate_redemption_txn.sql
│       ├── assert_redemption_member_exists.sql
│       └── assert_raw_field_count_matches_spec.sql
├── airflow/
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   ├── requirements.txt
│   ├── .env.example
│   ├── scripts/
│   │   ├── convert_aus_xlsx_to_csv.py
│   │   └── snowflake_tasks.py
│   └── dags/
│       └── skypoints_daily_pipeline.py
├── .github/workflows/ci.yml
└── Makefile
```

---

## 3. Component Inventory

| Component | Type | Purpose | Input | Output |
|---|---|---|---|---|
| `pytest.ini` | Test config | `testpaths = tests`, `pythonpath = demo airflow/scripts` — makes both Python components importable as top-level modules by their tests, matching how they run as standalone scripts | — | — |
| `requirements.txt` / `requirements-dev.txt` | Dependency manifest | Runtime (`openpyxl`) vs. test-only (`pytest`) dependencies for the Python components | — | — |
| `tests/test_generate_sample_feed.py` | pytest suite | Defines the contract for `demo/generate_sample_feed.py` ahead of its implementation (docs/04 Red step): required edge cases (AUS literal `"NULL"`, invalid date string, ambiguous USA date, IND membership-type values), file output shape, and a same-`member_key`-different-run-date attribute change | — | pass/fail |
| `tests/test_convert_aus_xlsx_to_csv.py` | pytest suite | Defines the contract for `airflow/scripts/convert_aus_xlsx_to_csv.py` ahead of its implementation: header/text passthrough (`"NULL"`, invalid date strings unchanged), deterministic ISO formatting of real datetime cells, clear failure on a missing source file | — | pass/fail |
| `demo/generate_sample_feed.py` | Python script | Produces per-country fixture files for a given run date, including known edge cases (ambiguous USA dates, AUS `"NULL"` string, IND `Individual or Corporate` values, a member reappearing under a different country across two run dates) | `--run-date` | `landing/*.xlsx`, `landing/*.csv`, `landing/*.json` |
| `setup/snowflake_bootstrap.sql` | SQL script | One-time Snowflake environment provisioning | — | databases/schemas/warehouses/roles/stages/file formats/resource monitor |
| `setup/raw_tables.sql` | SQL script | RAW layer DDL — one string-typed table per source plus load metadata (docs/01 §5) | — | `RAW.AUS_MEMBER_PROFILE`, `RAW.IND_MEMBER_PROFILE`, `RAW.USA_MEMBER_PROFILE`, `RAW.REDEMPTION_FEED` |
| `setup/verify_raw_tables.sql` | SQL script | Confirms the four RAW tables and their columns exist as specified | — | pass/fail |
| `airflow/scripts/convert_aus_xlsx_to_csv.py` | Python script | Converts `AUS.xlsx` to CSV — Snowflake has no native Excel file format | `landing/aus_member_<date>.xlsx` | `landing/aus_member_<date>.csv` |
| `dbt/seeds/country_reference.csv` | dbt seed | Canonical country code list; drives `generate_country_tables` macro and the country-code validation test | — | `SEEDS.COUNTRY_REFERENCE` |
| `dbt/seeds/tier_reference.csv` | dbt seed | Reference list of valid tier codes | — | `SEEDS.TIER_REFERENCE` |
| `stg_member_profile_aus.sql` | dbt model | Harmonizes `RAW.AUS_MEMBER_PROFILE` into the canonical schema; `TRY_TO_DATE` handling for `"NULL"`/invalid strings | `RAW.AUS_MEMBER_PROFILE` | canonical-shape rows, `country_code='AUS'` |
| `stg_member_profile_ind.sql` | dbt model | Harmonizes `RAW.IND_MEMBER_PROFILE`; parses `M/D/YYYY`; maps `Individual or Corporate` → `membership_type` | `RAW.IND_MEMBER_PROFILE` | canonical-shape rows, `country_code='IND'` |
| `stg_member_profile_usa.sql` | dbt model | Harmonizes `RAW.USA_MEMBER_PROFILE`; parses concatenated dates deterministically only (via `parse_usa_date`), quarantines ambiguous ones to `NULL`; `dob` always `NULL` | `RAW.USA_MEMBER_PROFILE` | canonical-shape rows, `country_code='USA'` |
| `stg_member_profile.sql` | dbt model | `UNION ALL` of the three source-specific models | the three models above | `STAGING.MEMBER_PROFILE` |
| `extract_feed_date.sql` (macro) | dbt macro | Extracts the business `feed_date` from a source file name (e.g. `aus_member_20240115.csv`) | `source_file_name` | `feed_date` |
| `parse_usa_date.sql` (macro) | dbt macro | Parses USA's concatenated digit-string dates; resolves to `NULL` (not a guess) when two calendar-valid splits exist | raw digit string | `DATE` or `NULL` |
| `_staging__models.yml` | dbt schema tests | `not_null`/`unique` on `member_key`; `not_null` on `member_id`, `member_name`, `enrollment_date`, `country_code`, `age` range; `not_null` on `stg_redemptions.txn_id`/`member_id` | staging models | pass/fail |
| `stg_redemptions.sql` | dbt model | Flattens `RAW.REDEMPTION_FEED.payload:redemptions` via `LATERAL FLATTEN` | `RAW.REDEMPTION_FEED` | `STAGING.REDEMPTIONS` |
| `snap_member_country.sql` | dbt snapshot | SCD2 history of tracked attributes (`tier_code`, `last_flight_date`, `is_active`) per `member_key` — not `country_code`, which is fixed by construction (see `docs/01` §3, §7). Targets the `STAGING` schema (not a separate `SNAPSHOTS` schema — none is provisioned; same simplification as the seeds-schema fix in Phase 3) | `stg_member_profile` | `STAGING.SNAP_MEMBER_COUNTRY` |
| `int_member_profile_final.sql` | dbt model | Current-attribute resolution — snapshot rows where `dbt_valid_to IS NULL` | `STAGING.SNAP_MEMBER_COUNTRY` | `MARTS.INT_MEMBER_PROFILE_FINAL` |
| `generate_country_tables.sql` (model) | dbt model | Thin wrapper that invokes the `generate_country_tables` macro as a side effect of `dbt run --select marts`; own output is an audit row only | `int_member_profile_final`, `country_reference` | `MARTS.TABLE_<COUNTRY>` per country + an audit row |
| `_marts__models.yml` | dbt schema tests | `not_null`/`unique` on `int_member_profile_final.member_key`; `not_null` on `redemptions.txn_id`; `accepted_values` on `redemptions.match_status` | marts models | pass/fail |
| `redemptions.sql` | dbt model | Joins `stg_redemptions` to `int_member_profile_final` on `member_id`; classifies each row `RESOLVED`/`AMBIGUOUS`/`ORPHAN` rather than assuming a clean join (docs/01 §7); global (not split by country) | both models above | `MARTS.REDEMPTIONS` |
| `assert_no_duplicate_redemption_txn.sql`, `assert_redemption_member_exists.sql` | dbt singular tests | `txn_id` uniqueness; every `RESOLVED` redemption's `member_key` actually exists (not a rule against `ORPHAN`/`AMBIGUOUS` rows, which are expected) | `stg_redemptions`, `redemptions` | pass/fail |
| `calculate_age.sql` (macro) | dbt macro | Age calculation per design spec §6.1 | `dob`, `feed_date` | `age` |
| `is_stale_member.sql` (macro) | dbt macro | Stale-member flag per design spec §6.2 | `last_flight_date`, `feed_date` | `stale_member_flag` |
| `tests/singular/*.sql` | dbt tests | One test per validation rule in design spec §8 | staging/marts models | pass/fail, logged |
| `snowflake_tasks.py` | Python module | Task business logic (connection handling, SQL construction, per-source staging, run summary) extracted from the DAG file so it's unit-testable without Airflow importable — see `tests/test_snowflake_tasks.py` | — | — |
| `skypoints_daily_pipeline.py` | Airflow DAG | Wires `snowflake_tasks` functions into tasks and dependencies; no business logic of its own | landing files | populated marts tables, test results |
| `Dockerfile` / `docker-compose.yaml` | Deployment | Airflow (`LocalExecutor`) + isolated dbt venv | — | running Airflow stack |
| `.github/workflows/ci.yml` | CI | `dbt build`/`test` on DuckDB target + DAG-integrity check | every push | pass/fail check |
| `Makefile` | Dev entrypoint | `bootstrap`, `up`, `down`, `demo`, `dbt-fast` targets | — | — |

---

## 4. Airflow DAG Specification

`skypoints_daily_pipeline` — `schedule_interval='@daily'`, `catchup=False`, `max_active_runs=1`, `retries=1`.

`landing/` (repo root, gitignored) is bind-mounted into the Airflow containers at `/opt/airflow/landing` (`airflow/docker-compose.yaml`). `FileSensor` tasks poll `/opt/airflow/landing/<source>_member_{{ ds_nodash }}.<ext>` (or `redemption_{{ ds_nodash }}.json`) — the naming convention `demo/generate_sample_feed.py` already writes — so each scheduled run only looks for that run's own dated file.

| Task ID | Operator | Upstream | Purpose |
|---|---|---|---|
| `check_aus_file`, `check_ind_file`, `check_usa_file`, `check_redemption_file` | `FileSensor` | — | wait for the day's landing files |
| `convert_aus_xlsx` | `PythonOperator` | `check_aus_file` | Excel → CSV |
| `stage_and_copy_aus` / `_ind` / `_usa` | `SnowflakeOperator` | respective file-ready task | `PUT` + `COPY INTO` per-source RAW table |
| `stage_and_copy_redemptions` | `SnowflakeOperator` | `check_redemption_file` | `PUT` + `COPY INTO` `RAW.REDEMPTION_FEED` |
| `dbt_seed` | `BashOperator` | all `stage_and_copy_*` | load `country_reference`, `tier_reference` |
| `dbt_run_staging` | `BashOperator` | `dbt_seed` | build `stg_member_profile*`, `stg_redemptions` |
| `dbt_snapshot` | `BashOperator` | `dbt_run_staging` | run `snap_member_country` — reads `stg_member_profile`, so must run after it exists |
| `dbt_run_marts` | `BashOperator` | `dbt_snapshot` | build `int_member_profile_final`, country tables, `redemptions` |
| `dbt_test` | `BashOperator` | `dbt_run_marts` | run the full test suite |
| `publish_run_summary` | `PythonOperator` | `dbt_test` | log row counts per country table and test pass/fail summary |

Idempotency: Snowflake's `COPY INTO` tracks load history per file name and skips a file already loaded; the snapshot only inserts a new row when a tracked attribute (`tier_code`, `last_flight_date`, `is_active`) actually changes — not on `country_code`, which is fixed by construction (`docs/01` §3, §7). Reruns of the same DAG run are therefore safe without extra bookkeeping.

---

## 5. Build Sequence

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 1 — Scaffold | repo skeleton, `docker-compose.yaml`, `dbt_project.yml`, `setup/snowflake_bootstrap.sql` | Snowflake objects exist; empty dbt project runs |
| 2 — Fixtures + raw | `generate_sample_feed.py`, `convert_aus_xlsx_to_csv.py`, RAW tables | fixture generator and converter pass their tests (`tests/`); RAW tables exist and are verified (`setup/verify_raw_tables.sql`). Actually loading a fixture set is deliberately deferred to Phase 8 — the `PUT`/`COPY INTO` logic is Airflow's `stage_and_copy_*` tasks, not a throwaway manual script |
| 3 — Harmonization | `stg_member_profile_aus/_ind/_usa`, `stg_member_profile` | union produces one canonical-shape row per source member, correct `member_key`/`country_code` |
| 4 — Derived columns | `calculate_age`, `is_stale_member` macros | Age/Stale_Member correct against fixtures with known DOB/flight dates, including `NULL`-DOB (USA) rows |
| 5 — Attribute history + country split | `snap_member_country`, `int_member_profile_final`, `generate_country_tables` | a member's tracked attribute (e.g. `tier_code`) changed between two fixture run dates produces two snapshot versions for the same `member_key`; a genuine country change (a new `member_key` in a different source) lands only in the new country's table, per the acknowledged non-linkage limitation in `docs/01` §3 |
| 6 — Redemptions | `stg_redemptions`, `redemptions.sql` | flattened row count matches fixture array lengths; the three fixture redemptions classify as RESOLVED, AMBIGUOUS, and ORPHAN respectively, matching `demo/generate_sample_feed.py`'s member_id design |
| 7 — Validation | `tests/singular/*.sql`, schema tests | every fixture-injected defect (ID collisions, ambiguous USA dates, invalid AUS dates, bad country codes, duplicate txn, raw field-count mismatch) is caught, none silently passes |
| 8 — Orchestration | `skypoints_daily_pipeline.py` | DAG runs the full sequence end to end against a fixture day, including the first actual `PUT`/`COPY INTO` load of a generated fixture set into all four RAW tables (Phase 2's exit criterion, deferred here) |
| 9 — CI + demo polish | `ci.yml`, `DEMO_RUNBOOK.md` | CI green on push; demo runbook reproduces phases 5–7 live |

---

## 6. Traceability to Assessment Deliverables

| Deliverable | Satisfied by |
|---|---|
| 1 — DDL for raw/staging/country tables | `setup/snowflake_bootstrap.sql`, RAW tables (§3), `stg_member_profile` (§3), `generate_country_tables` macro |
| 2 — Staging load with Age/Stale_Member | `calculate_age`, `is_stale_member` macros, `stg_member_profile.sql` |
| 3 — Country split with "latest record wins" | `snap_member_country` snapshot, `int_member_profile_final`, `generate_country_tables` macro |
| 4 — JSON flatten + join | `stg_redemptions.sql`, `redemptions.sql` |
| 5 — Data validations | `tests/singular/*.sql`, schema tests in `_staging__sources.yml` |
| 6 — Live demonstration | `demo/generate_sample_feed.py`, `demo/DEMO_RUNBOOK.md`, Airflow UI run against Snowflake |
