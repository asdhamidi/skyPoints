{#
  Canonical member profile — union of the three per-source harmonization
  models (docs/01_Design_Specification.md §5, §6), plus the derived Age and
  Stale_Member_Flag columns (docs/01 §6.1, §6.2), computed here rather than
  per-source since the logic is identical once every row shares the same
  dob / last_flight_date / feed_date shape.
#}

with aus as (
    select * from {{ ref('stg_member_profile_aus') }}
),

ind as (
    select * from {{ ref('stg_member_profile_ind') }}
),

usa as (
    select * from {{ ref('stg_member_profile_usa') }}
),

unioned as (
    select * from aus
    union all
    select * from ind
    union all
    select * from usa
),

final as (

    select
        *,
        {{ calculate_age('dob', 'feed_date') }}                as age,
        {{ is_stale_member('last_flight_date', 'feed_date') }} as stale_member_flag
    from unioned

)

select * from final
