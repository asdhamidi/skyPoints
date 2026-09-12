{#
  Attribute history per member_key (docs/01_Design_Specification.md §6.3).
  check_cols is deliberately tier_code / last_flight_date / is_active only —
  NOT country_code, which is already baked into member_key itself (docs/01 §3),
  so a country change can never appear as a version of an existing key; it can
  only appear as an entirely new, uncorrelated member_key. dob and
  enrollment_date are excluded too: they're fixed historical facts for a given
  member_key, not attributes expected to change.
#}

{% snapshot snap_member_country %}

{{
    config(
      target_schema='STAGING',
      unique_key='member_key',
      strategy='check',
      check_cols=['tier_code', 'last_flight_date', 'is_active'],
    )
}}

select * from {{ ref('stg_member_profile_valid') }}

{% endsnapshot %}
