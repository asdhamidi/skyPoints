-- SkyPoints — RAW table verification.
-- Run after setup/raw_tables.sql. Each statement should return the expected shape with no error.

SHOW TABLES LIKE '%MEMBER_PROFILE' IN SCHEMA SKYPOINTS.RAW;   -- expect AUS_, IND_, USA_MEMBER_PROFILE
SHOW TABLES LIKE 'REDEMPTION_FEED' IN SCHEMA SKYPOINTS.RAW;    -- expect 1 row

DESCRIBE TABLE SKYPOINTS.RAW.AUS_MEMBER_PROFILE;   -- expect 8 columns, all VARCHAR except load_ts
DESCRIBE TABLE SKYPOINTS.RAW.IND_MEMBER_PROFILE;   -- expect 9 columns, all VARCHAR except load_ts
DESCRIBE TABLE SKYPOINTS.RAW.USA_MEMBER_PROFILE;   -- expect 7 columns, all VARCHAR except load_ts
DESCRIBE TABLE SKYPOINTS.RAW.REDEMPTION_FEED;      -- expect payload VARIANT, source_file_name VARCHAR, load_ts TIMESTAMP_NTZ

-- SKYPOINTS_LOADER should already be able to read/write these (granted on ALL/FUTURE TABLES
-- IN SCHEMA RAW by setup/snowflake_bootstrap.sql §7) without any new grant.
SHOW GRANTS ON TABLE SKYPOINTS.RAW.AUS_MEMBER_PROFILE;
