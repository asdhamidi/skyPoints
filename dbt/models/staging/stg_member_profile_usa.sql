{#
  Harmonizes RAW.USA_MEMBER_PROFILE into the canonical member profile shape
  (docs/01_Design_Specification.md §1, §2). USA.csv carries no DOB column at
  all (dob is always NULL here) and dates are concatenated digit strings with
  no delimiter; parse_usa_date (macros/parse_usa_date.sql) parses only when
  the digit count and calendar validity force a single unique split, and
  returns NULL — not a guess — for a genuinely ambiguous value (docs/01 §4).

  The *_raw columns carry the original unparsed string through so a failed
  parse can be explained in the DLQ (rejected_member_records.sql) rather than
  just showing up as an unexplained NULL — see docs/01 §10. dob_raw is always
  NULL: USA.csv never carries a DOB value at all, so there is nothing to show.
#}

with source as (

    select * from {{ source('raw', 'usa_member_profile') }}

),

renamed as (

    select
        'USA-' || id                                       as member_key,
        id                                                  as member_id,
        name                                                as member_name,
        cast(null as date)                                  as dob,
        {{ parse_usa_date('enrollment_date') }}             as enrollment_date,
        {{ parse_usa_date('flight_date') }}                 as last_flight_date,
        tier_code                                           as tier_code,
        cast(null as varchar)                               as agent_name,
        cast(null as varchar)                               as state,
        'USA'                                                as country_code,
        cast(null as varchar)                               as post_code,
        cast(null as varchar)                               as is_active,
        cast(null as varchar)                               as membership_type,
        'USA'                                                as source_system,
        {{ extract_feed_date('source_file_name') }}         as feed_date,
        load_ts                                             as load_ts,
        cast(null as varchar)                               as dob_raw,
        enrollment_date                                     as enrollment_date_raw,
        flight_date                                         as last_flight_date_raw
    from source

)

select * from renamed
