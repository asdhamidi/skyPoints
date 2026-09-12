{#
  Harmonizes RAW.IND_MEMBER_PROFILE into the canonical member profile shape
  (docs/01_Design_Specification.md §1, §2). Dates are US-style M/D/YYYY text
  (docs/01 §4); individual_or_corporate maps to membership_type, a field with
  no home in the canonical layout otherwise.

  Snowflake's TO_DATE/TRY_TO_DATE format model accepts both 1- and 2-digit
  values for MM/DD even when the mask specifies two digits — 'MM/DD/YYYY'
  parses "1/1/2022" as well as "12/13/1982" without a second format variant.
  Confirmed against the real values on a live run.

  The *_raw columns carry the original unparsed string through so a failed
  parse can be explained in the DLQ (rejected_member_records.sql) rather than
  just showing up as an unexplained NULL — see docs/01 §10.

  Incremental, merged by member_key (docs/01 §11) — see stg_member_profile_aus.sql
  for the full reasoning; identical pattern here.
#}

{{ config(materialized='incremental', unique_key='member_key') }}

with source as (

    select * from {{ source('raw', 'ind_member_profile') }}

    {% if is_incremental() %}
    where load_ts > (select coalesce(max(load_ts), '1900-01-01'::timestamp_ntz) from {{ this }})
    {% endif %}

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
        load_ts                                            as load_ts,
        dob                                                 as dob_raw,
        enrollment_date                                     as enrollment_date_raw,
        flight_date                                         as last_flight_date_raw
    from source

)

select * from renamed
qualify row_number() over (partition by member_key order by load_ts desc) = 1
