-- SkyPoints — RAW layer table DDL.
-- Run once, after setup/snowflake_bootstrap.sql. One table per source, string-typed
-- (schema-on-read, no casting on load) plus load metadata — see
-- docs/01_Design_Specification.md §3, §5.
-- Verify afterwards with setup/verify_raw_tables.sql.

USE ROLE ACCOUNTADMIN;
USE DATABASE SKYPOINTS;
USE SCHEMA RAW;

-- AUS.xlsx, converted to CSV by airflow/scripts/convert_aus_xlsx_to_csv.py before load —
-- date_of_birth and date_of_enrollment are VARCHAR, not DATE, so the literal "NULL" string
-- and the invalid "2021-13-13" string (docs/01 §2, §4) land unchanged, for staging to parse
-- deliberately rather than have COPY INTO silently reject or coerce them.
CREATE TABLE IF NOT EXISTS RAW.AUS_MEMBER_PROFILE (
  unique_id           VARCHAR,
  member_name         VARCHAR,
  tier_type           VARCHAR,
  date_of_birth       VARCHAR,
  date_of_enrollment  VARCHAR,
  date_of_flight      VARCHAR,
  source_file_name    VARCHAR,
  load_ts             TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- IND.csv — dates are M/D/YYYY text; individual_or_corporate has no home in the canonical
-- schema until staging maps it to membership_type (docs/01 §1, §2).
CREATE TABLE IF NOT EXISTS RAW.IND_MEMBER_PROFILE (
  id                        VARCHAR,
  name                      VARCHAR,
  dob                       VARCHAR,
  tier_code                 VARCHAR,
  enrollment_date           VARCHAR,
  individual_or_corporate   VARCHAR,
  flight_date               VARCHAR,
  source_file_name          VARCHAR,
  load_ts                   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- USA.csv — no DOB column at all (docs/01 §2); dates are concatenated digit strings,
-- some genuinely ambiguous (docs/01 §4) and left as-is here for staging to parse defensively.
CREATE TABLE IF NOT EXISTS RAW.USA_MEMBER_PROFILE (
  id                  VARCHAR,
  name                VARCHAR,
  tier_code           VARCHAR,
  enrollment_date     VARCHAR,
  flight_date         VARCHAR,
  source_file_name    VARCHAR,
  load_ts             TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Redemption JSON feed — one row per member-day document (docs/01 §2), landed whole as
-- VARIANT; stg_redemptions flattens payload:redemptions via LATERAL FLATTEN (docs/01 §7).
CREATE TABLE IF NOT EXISTS RAW.REDEMPTION_FEED (
  payload             VARIANT,
  source_file_name    VARCHAR,
  load_ts             TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
