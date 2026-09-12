-- dbt singular test: fails (returns rows) if a RAW row is missing its
-- source's defining name field even though the row otherwise exists — the
-- practical signature of a field-count/column-alignment mismatch that
-- slipped through COPY INTO (docs/01_Design_Specification.md §8). The
-- stronger protection is at load time: setup/snowflake_bootstrap.sql's
-- CSV_FORMAT sets ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE, so a row with the
-- wrong field count is rejected before it ever reaches these tables — this
-- test is the defense-in-depth check for whatever gets through anyway
-- (e.g. a row with the right count but genuinely blank/malformed content).

select 'aus' as source_name, unique_id as source_row_id, source_file_name
from {{ source('raw', 'aus_member_profile') }}
where member_name is null

union all

select 'ind' as source_name, id as source_row_id, source_file_name
from {{ source('raw', 'ind_member_profile') }}
where name is null

union all

select 'usa' as source_name, id as source_row_id, source_file_name
from {{ source('raw', 'usa_member_profile') }}
where name is null
