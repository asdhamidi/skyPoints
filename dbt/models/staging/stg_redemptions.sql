{#
  Flattens RAW.REDEMPTION_FEED.payload:redemptions into one row per
  transaction (docs/01_Design_Specification.md §7). member_id is carried
  through unchanged and unresolved here — country attribution happens in
  marts/redemptions.sql, since it depends on int_member_profile_final.
#}

with source as (

    select * from {{ source('raw', 'redemption_feed') }}

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
