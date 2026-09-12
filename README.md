# SkyPoints

Data pipeline for a global airline loyalty program: per-country member profile ingestion and mileage-redemption processing, built on Snowflake, dbt, and Airflow.

## Overview

SkyPoints maintains member profiles per country (Australia, India, USA) and a daily JSON feed of partner mileage redemptions. This repository ingests both, harmonizes the per-country sources into a single canonical schema, tracks attribute history over time, splits members into per-country target tables, and joins redemptions back to member profiles — classifying each join rather than assuming it resolves cleanly, since member identifiers are not globally unique across sources.

## Architecture

```
AUS.xlsx / IND.csv / USA.csv --> RAW (per-source, string-typed)
                                     |
                          dbt harmonization models
                                     |
                           stg_member_profile (union, pre-validation)
                                     |
                                     |--> rejected_member_records (DLQ, incremental)
                                     |
                           stg_member_profile_valid
                                     |
                      dbt snapshot (attribute history)
                                     |
                       int_member_profile_final
                                     |
                      per-country MARTS.TABLE_<COUNTRY>

Redemption JSON --> RAW.REDEMPTION_FEED --> stg_redemptions (flattened)
                                                 |
                            marts.redemptions (RESOLVED / AMBIGUOUS / ORPHAN)
```

Stack: Snowflake (warehouse), dbt (transformation and tests), Airflow with `LocalExecutor` (orchestration), Docker Compose (local deployment).

## Scaling to Billions of Records

`RAW` tables are append-only and grow unbounded; a plain view or a full-table rebuild reprocesses that entire history on every run, which does not hold up at real billion-row/day volume. To address this:

- Staging harmonization models (`stg_member_profile_aus`/`_ind`/`_usa`, `stg_redemptions`) are incremental, filtered to only `RAW` rows newer than the last run and merged by `member_key`/`txn_id` - each run's cost is bounded by what's new, not by everything ever loaded.
- Per-country tables and `redemptions` are built with `MERGE`, not `CREATE OR REPLACE` - only new or changed rows are touched, not the entire table.

Full reasoning, including the two different incremental patterns used (dimension-style upsert for member profiles, fact-style append for redemptions) and a documented consequence for snapshot history, is in `docs/01` section 11.

**Caveat**: ingestion in this build lands each day's file in a local `landing/` folder and uploads it via a Python function (`snowflake-connector-python`'s `PUT`, triggered by an Airflow `FileSensor`) - reasonable for a single-machine demo, not how this would be built for real continuous high-volume ingestion. The production equivalent, already noted as a drop-in swap in `docs/02` section 2, is landing files in cloud object storage (e.g. S3) behind a Snowflake external stage, with Snowpipe for continuous ingestion instead of a scheduled local `PUT` - nothing downstream of `COPY INTO` would need to change.

## Snowflake Data Objects

### RAW schema

| Object | Type | Purpose |
|---|---|---|
| `AUS_MEMBER_PROFILE` | Table | Landed AUS extract, string-typed, no casting on load |
| `IND_MEMBER_PROFILE` | Table | Landed IND extract |
| `USA_MEMBER_PROFILE` | Table | Landed USA extract |
| `REDEMPTION_FEED` | Table | Landed redemption JSON, one row per document, `payload` as VARIANT |

### STAGING schema

| Object | Type | Purpose |
|---|---|---|
| `stg_member_profile_aus` | Table (incremental) | Harmonizes `RAW.AUS_MEMBER_PROFILE` into the canonical schema; only new `RAW` rows processed per run, merged by `member_key` |
| `stg_member_profile_ind` | Table (incremental) | Harmonizes `RAW.IND_MEMBER_PROFILE`; maps `Individual or Corporate` to `membership_type`; incremental, merged by `member_key` |
| `stg_member_profile_usa` | Table (incremental) | Harmonizes `RAW.USA_MEMBER_PROFILE`; parses concatenated dates defensively, never guessing an ambiguous one; incremental, merged by `member_key` |
| `stg_member_profile` | View | Union of the three models above, plus derived `age` and `stale_member_flag`. Pre-validation - still contains rejected rows; nothing downstream reads this directly |
| `stg_member_profile_valid` | View | `stg_member_profile` with rows missing a mandatory field (`member_name`, `member_id`, `enrollment_date`) excluded. The snapshot and everything after it is built on this, not `stg_member_profile` |
| `rejected_member_records` | Table (incremental) | Dead-letter queue: the inverse of the gate above, with a `rejection_reason` per row. Append-only, so a repeat rejection on a later day stays visible rather than being collapsed |
| `stg_redemptions` | Table (incremental) | Flattens the redemption JSON via `LATERAL FLATTEN`, one row per transaction; only new `RAW` rows processed per run, merged by `txn_id` |
| `snap_member_country` | Table (dbt snapshot) | SCD2 history of `tier_code`, `last_flight_date`, `is_active` per `member_key` - not `country_code`, which is fixed at key creation |
| `country_reference` | Table (dbt seed) | Canonical country code list; drives per-country table generation and country-code validation |

### MARTS schema

| Object | Type | Purpose |
|---|---|---|
| `int_member_profile_final` | Table | Current attribute values per `member_key` - the open (`dbt_valid_to IS NULL`) snapshot row |
| `TABLE_AUS`, `TABLE_IND`, `TABLE_USA` | Table (generated, merged) | One physical table per country in `country_reference`, produced by a single macro loop; `MERGE`d each run, not rebuilt from scratch |
| `redemptions` | Table (incremental) | Redemptions joined to member profile on `member_id`, classified `RESOLVED`, `AMBIGUOUS`, or `ORPHAN`; only new transactions processed per run, merged by `txn_id` |

## Repository Structure

```
skyPoints/
    docs/                 Design and build documentation
    setup/                Snowflake bootstrap and verification SQL
    dbt/                  dbt project - models, snapshots, macros, seeds, tests
    airflow/               Airflow deployment - DAG, task modules, Dockerfile
    demo/                 Fixture data generator
    tests/                Python unit tests (pytest)
    Makefile
    requirements.txt, requirements-dev.txt
```

## Documentation

| Document | Covers |
|---|---|
| `docs/01_Design_Specification.md` | Canonical schema, source mapping, transformation and validation rules |
| `docs/02_Tech_Stack_Specification.md` | Platform configuration - Snowflake, dbt, Airflow, CI, secrets |
| `docs/03_Technical_Build_Plan.md` | Architecture, component inventory, build sequence |
| `docs/04_Engineering_Practices.md` | Development process - test-first, commit discipline |
| `docs/05_Source_Data_Analysis.md` | Findings from the supplied source files |

## Getting Started

### Prerequisites

- Docker Engine with the Compose plugin
- Python 3.10+
- A Snowflake account, bootstrapped per `setup/snowflake_bootstrap.sql` (includes RSA key-pair generation for the service user)

### Setup

```bash
pip install -r requirements-dev.txt
cp airflow/.env.example airflow/.env
cp dbt/profiles/profiles.yml.example dbt/profiles/profiles.yml
```

Fill in the Snowflake connection details in `airflow/.env` (account identifier, private key path, warehouse, database, role). `dbt/profiles/profiles.yml` needs no edits - it reads the same environment variables.

### Run

```bash
python demo/generate_sample_feed.py --run-date 2024-01-15 --out-dir landing
cd airflow && docker compose up -d --build
```

The fixture generator defaults to 250,000 bulk records per source on top of the fixed edge-case rows (`--record-count` to override - e.g. a small value for a quick smoke test).

In the Airflow UI (`localhost:8080`, `admin`/`admin`), unpause `skypoints_daily_pipeline` and trigger it for the same logical date used above.

## Testing

```bash
pytest                                 # Python unit tests
cd dbt && dbt build --target duckdb    # dbt models and tests against DuckDB, no Snowflake required
```

## Key Design Decisions

- **Member identity**: `member_key = country_code-member_id`, since each source's local IDs are not globally unique across countries (`docs/01` section 3).
- **Redemption matching**: classified `RESOLVED`, `AMBIGUOUS`, or `ORPHAN` rather than assumed, since the redemption feed's member identifier carries the same ambiguity (`docs/01` section 7).
- **Attribute history**: tracked with a dbt snapshot, scoped to non-key attributes only - country is fixed at the point a member key is created, not something the snapshot resolves.
- **Country tables**: generated by a single macro over a seed list of countries, not written by hand per country.
- **Dead-letter queue**: a member row missing a mandatory field (e.g. an `enrollment_date` that failed to parse) is excluded from the main flow and routed to `rejected_member_records` with a reason, rather than propagating a silent `NULL` past a guarantee the rest of the design depends on (`docs/01` section 10).
