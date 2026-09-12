{#
  Dead-letter queue for member rows failing a mandatory-field check
  (docs/01_Design_Specification.md §8, §10) — the "reject row, log" and
  "quarantine, never guess" actions specified there but not actually built
  until now. A row lands here instead of stg_member_profile_valid.sql when
  member_name, member_id, or enrollment_date is null after parsing —
  including an enrollment_date that failed to parse at all (e.g. AUS's
  invalid "2021-13-13").

  Incremental and append-only: a source resending the same bad row on a later
  day is expected to reject again, so there's no unique_key collapsing repeat
  rejections into one — each is its own dated record, which is what lets you
  see whether a given defect is still happening or was fixed.
#}

{{
    config(
      materialized='incremental',
    )
}}

with candidates as (

    select
        coalesce(country_code, 'UNKNOWN') || '-' || coalesce(member_id, 'UNKNOWN') as attempted_member_key,
        member_id,
        member_name,
        source_system,
        feed_date,
        load_ts,
        dob_raw,
        enrollment_date_raw,
        last_flight_date_raw,
        case
            when member_name is null then 'MISSING_MEMBER_NAME'
            when member_id is null then 'MISSING_MEMBER_ID'
            when enrollment_date is null then
                'INVALID_ENROLLMENT_DATE: raw value was ' || coalesce('''' || enrollment_date_raw || '''', '<null>')
            else 'UNKNOWN_REJECTION_REASON'
        end as rejection_reason
    from {{ ref('stg_member_profile') }}
    where member_name is null
       or member_id is null
       or enrollment_date is null

)

select * from candidates

{% if is_incremental() %}
where load_ts > (select coalesce(max(load_ts), '1900-01-01'::timestamp_ntz) from {{ this }})
{% endif %}
