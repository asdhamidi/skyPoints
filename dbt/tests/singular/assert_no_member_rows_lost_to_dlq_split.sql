-- dbt singular test: fails (returns a row) if the row count for the most
-- recent feed_date in stg_member_profile doesn't exactly equal
-- stg_member_profile_valid + rejected_member_records for that same date —
-- i.e., the mandatory-field DLQ split (docs/01 §10) lost or duplicated a row
-- somewhere between the raw union and its two destinations.

with latest_feed_date as (
    select max(feed_date) as feed_date from {{ ref('stg_member_profile') }}
),

total_count as (
    select count(*) as total
    from {{ ref('stg_member_profile') }} m
    cross join latest_feed_date l
    where m.feed_date = l.feed_date
),

valid_count as (
    select count(*) as total
    from {{ ref('stg_member_profile_valid') }} m
    cross join latest_feed_date l
    where m.feed_date = l.feed_date
),

rejected_count as (
    select count(*) as total
    from {{ ref('rejected_member_records') }} m
    cross join latest_feed_date l
    where m.feed_date = l.feed_date
)

select
    (select total from total_count)    as total_rows,
    (select total from valid_count)    as valid_rows,
    (select total from rejected_count) as rejected_rows
where (select total from total_count)
   <> (select total from valid_count) + (select total from rejected_count)
