{#
  Harmonizes RAW.AUS_MEMBER_PROFILE into the canonical member profile shape
  (docs/01_Design_Specification.md §1, §2). member_key and country_code are
  assigned here, not read from any source column — AUS.xlsx carries no
  Country field at all; country is fixed by source identity.

  date_of_birth / date_of_enrollment are parsed with an explicit ISO format
  mask, matching what airflow/scripts/convert_aus_xlsx_to_csv.py writes for
  real datetime cells. The literal string "NULL" and the invalid string
  "2021-13-13" (docs/01 §2, §4) both fail this parse and resolve to NULL via
  TRY_TO_DATE, rather than erroring or being silently coerced.

  The *_raw columns carry the original unparsed string through so a failed
  parse can be explained in the DLQ (rejected_member_records.sql) rather than
  just showing up as an unexplained NULL — see docs/01 §10.
#}

with source as (

    select * from {{ source('raw', 'aus_member_profile') }}

),

renamed as (

    select
        'AUS-' || unique_id                              as member_key,
        unique_id                                         as member_id,
        member_name                                       as member_name,
        try_to_date(date_of_birth, 'YYYY-MM-DD')          as dob,
        try_to_date(date_of_enrollment, 'YYYY-MM-DD')     as enrollment_date,
        try_to_date(date_of_flight, 'YYYY-MM-DD')         as last_flight_date,
        tier_type                                         as tier_code,
        cast(null as varchar)                             as agent_name,
        cast(null as varchar)                             as state,
        'AUS'                                              as country_code,
        cast(null as varchar)                             as post_code,
        cast(null as varchar)                             as is_active,
        cast(null as varchar)                             as membership_type,
        'AUS'                                              as source_system,
        {{ extract_feed_date('source_file_name') }}       as feed_date,
        load_ts                                           as load_ts,
        date_of_birth                                     as dob_raw,
        date_of_enrollment                                as enrollment_date_raw,
        date_of_flight                                    as last_flight_date_raw
    from source

)

select * from renamed
