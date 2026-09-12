-- SkyPoints — Snowflake environment bootstrap.
-- Run once, manually, as ACCOUNTADMIN (or a role with CREATE DATABASE / WAREHOUSE / ROLE /
-- RESOURCE MONITOR privileges). Not part of the daily pipeline.
-- Reference: docs/02_Tech_Stack_Specification.md §2
-- Verify afterwards with setup/verify_bootstrap.sql.

USE ROLE ACCOUNTADMIN;

-- 1. Database and schemas ---------------------------------------------------
CREATE DATABASE IF NOT EXISTS SKYPOINTS;
CREATE SCHEMA IF NOT EXISTS SKYPOINTS.RAW;
CREATE SCHEMA IF NOT EXISTS SKYPOINTS.STAGING;
CREATE SCHEMA IF NOT EXISTS SKYPOINTS.MARTS;

-- 2. Warehouses --------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS LOAD_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE
  COMMENT = 'Raw ingestion (PUT / COPY INTO) workloads';

CREATE WAREHOUSE IF NOT EXISTS TRANSFORM_WH
  WAREHOUSE_SIZE = 'SMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE
  COMMENT = 'dbt transformation and test workloads';

-- 3. Roles ---------------------------------------------------------------
CREATE ROLE IF NOT EXISTS SKYPOINTS_LOADER;
CREATE ROLE IF NOT EXISTS SKYPOINTS_TRANSFORMER;

-- 4. File formats ----------------------------------------------------------
-- NULL_IF includes the literal string 'NULL' — AUS.xlsx (once converted to CSV) carries a
-- literal "NULL" text value in at least one DOB cell; this treats it as a true null on load
-- rather than a four-character string. See docs/01_Design_Specification.md §4.
-- ERROR_ON_COLUMN_COUNT_MISMATCH is Snowflake's default (TRUE) but is set explicitly here,
-- not left implicit: a row with more or fewer fields than the target table expects fails
-- the load rather than silently misaligning columns — directly answering the "field spec
-- says 11 columns, the sample file only has 10" mismatch catalogued in
-- docs/05_Source_Data_Analysis.md §3.
CREATE FILE FORMAT IF NOT EXISTS SKYPOINTS.RAW.CSV_FORMAT
  TYPE = CSV
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  NULL_IF = ('', 'NULL')
  ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE;

CREATE FILE FORMAT IF NOT EXISTS SKYPOINTS.RAW.JSON_FORMAT
  TYPE = JSON;

-- 5. Stages ------------------------------------------------------------------
CREATE STAGE IF NOT EXISTS SKYPOINTS.RAW.MEMBER_PROFILE_STAGE
  FILE_FORMAT = SKYPOINTS.RAW.CSV_FORMAT;

CREATE STAGE IF NOT EXISTS SKYPOINTS.RAW.REDEMPTION_STAGE
  FILE_FORMAT = SKYPOINTS.RAW.JSON_FORMAT;

-- 6. Resource monitor (guards trial-account credit usage) --------------------
CREATE RESOURCE MONITOR IF NOT EXISTS SKYPOINTS_MONITOR
  WITH CREDIT_QUOTA = 25
  TRIGGERS ON 80 PERCENT DO NOTIFY
            ON 100 PERCENT DO SUSPEND;

ALTER WAREHOUSE LOAD_WH      SET RESOURCE_MONITOR = SKYPOINTS_MONITOR;
ALTER WAREHOUSE TRANSFORM_WH SET RESOURCE_MONITOR = SKYPOINTS_MONITOR;

-- 7. Grants ----------------------------------------------------------------

-- SKYPOINTS_LOADER: raw ingestion only (Airflow's stage_and_copy_* tasks)
GRANT USAGE ON DATABASE SKYPOINTS TO ROLE SKYPOINTS_LOADER;
GRANT USAGE ON SCHEMA SKYPOINTS.RAW TO ROLE SKYPOINTS_LOADER;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA SKYPOINTS.RAW TO ROLE SKYPOINTS_LOADER;
GRANT SELECT, INSERT ON FUTURE TABLES IN SCHEMA SKYPOINTS.RAW TO ROLE SKYPOINTS_LOADER;
GRANT USAGE, READ, WRITE ON STAGE SKYPOINTS.RAW.MEMBER_PROFILE_STAGE TO ROLE SKYPOINTS_LOADER;
GRANT USAGE, READ, WRITE ON STAGE SKYPOINTS.RAW.REDEMPTION_STAGE TO ROLE SKYPOINTS_LOADER;
GRANT USAGE ON FILE FORMAT SKYPOINTS.RAW.CSV_FORMAT TO ROLE SKYPOINTS_LOADER;
GRANT USAGE ON FILE FORMAT SKYPOINTS.RAW.JSON_FORMAT TO ROLE SKYPOINTS_LOADER;
GRANT USAGE ON WAREHOUSE LOAD_WH TO ROLE SKYPOINTS_LOADER;

-- SKYPOINTS_TRANSFORMER: dbt — reads RAW, creates/reads in STAGING and MARTS
GRANT USAGE ON DATABASE SKYPOINTS TO ROLE SKYPOINTS_TRANSFORMER;
GRANT USAGE ON SCHEMA SKYPOINTS.RAW TO ROLE SKYPOINTS_TRANSFORMER;
GRANT SELECT ON ALL TABLES IN SCHEMA SKYPOINTS.RAW TO ROLE SKYPOINTS_TRANSFORMER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA SKYPOINTS.RAW TO ROLE SKYPOINTS_TRANSFORMER;
GRANT USAGE, CREATE TABLE, CREATE VIEW ON SCHEMA SKYPOINTS.STAGING TO ROLE SKYPOINTS_TRANSFORMER;
GRANT USAGE, CREATE TABLE, CREATE VIEW ON SCHEMA SKYPOINTS.MARTS TO ROLE SKYPOINTS_TRANSFORMER;
GRANT SELECT ON ALL TABLES IN SCHEMA SKYPOINTS.STAGING TO ROLE SKYPOINTS_TRANSFORMER;
GRANT SELECT ON ALL TABLES IN SCHEMA SKYPOINTS.MARTS TO ROLE SKYPOINTS_TRANSFORMER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA SKYPOINTS.STAGING TO ROLE SKYPOINTS_TRANSFORMER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA SKYPOINTS.MARTS TO ROLE SKYPOINTS_TRANSFORMER;
GRANT USAGE ON WAREHOUSE TRANSFORM_WH TO ROLE SKYPOINTS_TRANSFORMER;

-- 8. Service user for dbt AND ingestion --------------------------------------
-- Single service account used by both Airflow's stage_and_copy_* tasks (as
-- SKYPOINTS_LOADER — see airflow/dags/skypoints_daily_pipeline.py) and dbt's
-- `snowflake` target (as SKYPOINTS_TRANSFORMER — dbt/profiles/profiles.yml.example).
-- Holding both roles on one user keeps one credential set in .env rather than two;
-- each caller picks its role explicitly per connection, not via a fixed default.
--
-- Authenticated by RSA key pair, not a password: Snowflake has been actively
-- deprecating single-factor password auth (MFA enforcement rolling out
-- account-by-account), and password auth for a non-interactive service
-- account is the wrong pattern regardless — MFA can't be satisfied by a
-- pipeline. Generate the key pair once, locally (never commit the private key):
--
--   openssl genrsa -out keys/skypoints_dbt_rsa_key.p8 2048
--   openssl pkcs8 -topk8 -inform PEM -nocrypt \
--       -in keys/skypoints_dbt_rsa_key.p8 -out keys/skypoints_dbt_rsa_key.p8
--   openssl rsa -in keys/skypoints_dbt_rsa_key.p8 -pubout -out keys/skypoints_dbt_rsa_key.pub
--
-- Then paste the PUBLIC key's base64 body below (the .pub file's content,
-- excluding the "-----BEGIN/END PUBLIC KEY-----" lines). `keys/` is gitignored.
CREATE USER IF NOT EXISTS SKYPOINTS_DBT
  DEFAULT_ROLE = SKYPOINTS_TRANSFORMER
  DEFAULT_WAREHOUSE = TRANSFORM_WH
  DEFAULT_NAMESPACE = SKYPOINTS.STAGING
  COMMENT = 'Service account used by both Airflow ingestion and dbt transformations (key-pair auth)';

-- A separate ALTER (not folded into CREATE ... IF NOT EXISTS) so re-running this
-- script also applies a rotated key to an already-existing user — CREATE USER IF
-- NOT EXISTS is a no-op on an existing user and would silently skip a key update.
ALTER USER SKYPOINTS_DBT SET RSA_PUBLIC_KEY = '<PASTE_PUBLIC_KEY_BODY_HERE>';

GRANT ROLE SKYPOINTS_TRANSFORMER TO USER SKYPOINTS_DBT;
GRANT ROLE SKYPOINTS_LOADER TO USER SKYPOINTS_DBT;
