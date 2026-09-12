{#
  Flattens RAW.REDEMPTION_FEED.payload:redemptions into one row per
  transaction (docs/01_Design_Specification.md §7). member_id is carried
  through unchanged and unresolved here — country attribution happens in
  marts/redemptions.sql, since it depends on int_member_profile_final.

  Incremental, merged by txn_id (docs/01 §11). Unlike the per-source member
  profile models, this is a fact table, not a dimension — transactions are
  never expected to change once written, so this is really append-driven;
  unique_key on txn_id exists to make a resent/reprocessed file idempotent
  (upsert instead of a duplicate row) rather than to model "latest wins" the
  way member_key does for profiles.
#}

{{ config(materialized='incremental', unique_key='txn_id') }}

with source as (

    select * from {{ source('raw', 'redemption_feed') }}

    {% if is_incremental() %}
    where load_ts > (select coalesce(max(load_ts), '1900-01-01'::timestamp_ntz) from {{ this }})
    {% endif %}

),

flattened as (

    select
        source.payload:member_id::varchar                          as member_id,
        to_date(source.payload:feed_date::varchar, 'YYYYMMDD')      as feed_date,
        txn.value:txn_id::varchar                                   as txn_id,
        to_date(txn.value:txn_date::varchar, 'YYYYMMDD')            as txn_date,
        txn.value:partner::varchar                                  as partner,
        txn.value:miles_redeemed::number                            as miles_redeemed,
        txn.value:status::varchar                                   as status,
        source.source_file_name                                     as source_file_name,
        source.load_ts                                              as load_ts
    from source,
    lateral flatten(input => source.payload:redemptions) txn

)

select * from flattened
qualify row_number() over (partition by txn_id order by load_ts desc) = 1
