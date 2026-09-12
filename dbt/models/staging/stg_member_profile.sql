{#
  Canonical member profile — union of the three per-source harmonization
  models (docs/01_Design_Specification.md §5, §6). Age and Stale_Member_Flag
  are added in Phase 4 (docs/03_Technical_Build_Plan.md §5); this model
  intentionally does not include them yet.
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
)

select * from unioned
