{#
  Harmonizes RAW.IND_MEMBER_PROFILE into the canonical member profile shape
  (docs/01_Design_Specification.md §1, §2). Dates are US-style M/D/YYYY text
  (docs/01 §4); individual_or_corporate maps to membership_type, a field with
  no home in the canonical layout otherwise.

  NOTE: Snowflake's TO_DATE/TRY_TO_DATE format model is documented to accept
  both 1- and 2-digit values for MM/DD even when the mask specifies two
  digits — so 'MM/DD/YYYY' parses "1/1/2022" as well as "12/13/1982" without
  a second format variant. Worth confirming against the real values when this
  is run for the first time (docs/04 — the first red/green cycle for dbt
  happens on your machine, not in this sandbox).
#}

with source as (

    select * from {{ source('raw', 'ind_member_profile') }}

),

renamed as (

    select
        'IND-' || id                                      as member_key,
        id                                                 as member_id,
        name                                               as member_name,
        try_to_date(dob, 'MM/DD/YYYY')                     as dob,
        try_to_date(enrollment_date, 'MM/DD/YYYY')         as enrollment_date,
        try_to_date(flight_date, 'MM/DD/YYYY')             as last_flight_date,
        tier_code                                          as tier_code,
        cast(null as varchar)                              as agent_name,
        cast(null as varchar)                              as state,
        'IND'                                               as country_code,
        cast(null as varchar)                              as post_code,
        cast(null as varchar)                              as is_active,
        individual_or_corporate                            as membership_type,
        'IND'                                               as source_system,
        {{ extract_feed_date('source_file_name') }}        as feed_date,
        load_ts                                            as load_ts
    from source

)

select * from renamed
