{#
  Mandatory-field gate (docs/01_Design_Specification.md §8, §10): rows
  missing member_name, member_id, or enrollment_date — including a row whose
  enrollment_date failed to parse into a real date — are excluded here and
  routed to rejected_member_records.sql instead. This is the model everything
  downstream (the snapshot, marts) is built on, not stg_member_profile itself,
  which still carries rejected rows and diagnostic *_raw columns.

  Selects the canonical column set only — the *_raw passthrough columns exist
  for the DLQ's benefit and have no home in the canonical schema (docs/01 §1).
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
from {{ ref('stg_member_profile') }}
where member_name is not null
  and member_id is not null
  and enrollment_date is not null
