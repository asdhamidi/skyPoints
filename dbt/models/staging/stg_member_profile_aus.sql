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

  Incremental, merged by member_key (docs/01 §11): only RAW rows newer than
  what's already been processed are read each run, and a member_key already
  present gets updated in place rather than duplicated — this is what keeps a
  daily run's cost bounded to what's new, instead of rescanning RAW's entire
  ever-growing history every time. QUALIFY collapses to one row per
  member_key even if this run's own batch contains more than one (e.g.
  catching up several backlogged days at once).
#}

{{ config(materialized='incremental', unique_key='member_key') }}

with source as (

    select * from {{ source('raw', 'aus_member_profile') }}

    {% if is_incremental() %}
    where load_ts > (select coalesce(max(load_ts), '1900-01-01'::timestamp_ntz) from {{ this }})
    {% endif %}

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
qualify row_number() over (partition by member_key order by load_ts desc) = 1
