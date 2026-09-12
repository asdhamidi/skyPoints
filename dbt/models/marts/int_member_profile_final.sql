{#
  Current-attribute resolution (docs/01_Design_Specification.md §6.4): the
  single source of truth for a member's current tier/flight-date/status.
  Which physical country table a member_key belongs to is fixed at the point
  the key is created (docs/01 §3), not something this model or the snapshot
  resolves — country_code passes through unchanged from stg_member_profile.
#}

select
    member_key,
    member_id,
    member_name,
    dob,
    enrollment_date,
    last_flight_date,
    tier_code,
    agent_name,
    state,
    country_code,
    post_code,
    is_active,
    membership_type,
    age,
    stale_member_flag,
    source_system,
    feed_date,
    load_ts
from {{ ref('snap_member_country') }}
where dbt_valid_to is null
