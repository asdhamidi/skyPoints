-- SkyPoints — bootstrap verification.
-- Run after setup/snowflake_bootstrap.sql. Each statement should return the object(s)
-- named in the comment, with no error. This is the "green" check for Phase 1 (see
-- docs/03_Technical_Build_Plan.md §5) in the absence of an automated test runner against
-- a live Snowflake account.

SHOW DATABASES LIKE 'SKYPOINTS';                     -- expect 1 row: SKYPOINTS

SHOW SCHEMAS IN DATABASE SKYPOINTS;                  -- expect RAW, STAGING, MARTS (plus INFORMATION_SCHEMA/PUBLIC)

SHOW WAREHOUSES LIKE 'LOAD_WH';                      -- expect 1 row, SIZE = XSMALL
SHOW WAREHOUSES LIKE 'TRANSFORM_WH';                 -- expect 1 row, SIZE = SMALL

SHOW ROLES LIKE 'SKYPOINTS_%';                        -- expect SKYPOINTS_LOADER, SKYPOINTS_TRANSFORMER

SHOW FILE FORMATS IN SCHEMA SKYPOINTS.RAW;            -- expect CSV_FORMAT, JSON_FORMAT

SHOW STAGES IN SCHEMA SKYPOINTS.RAW;                  -- expect MEMBER_PROFILE_STAGE, REDEMPTION_STAGE

SHOW RESOURCE MONITORS LIKE 'SKYPOINTS_MONITOR';      -- expect 1 row, CREDIT_QUOTA = 25

-- Grant sanity checks — confirm each role actually has the access it needs
SHOW GRANTS TO ROLE SKYPOINTS_LOADER;
SHOW GRANTS TO ROLE SKYPOINTS_TRANSFORMER;

SHOW USERS LIKE 'SKYPOINTS_DBT';                      -- expect 1 row, DEFAULT_ROLE = SKYPOINTS_TRANSFORMER
SHOW GRANTS TO USER SKYPOINTS_DBT;                    -- expect BOTH SKYPOINTS_TRANSFORMER and SKYPOINTS_LOADER
