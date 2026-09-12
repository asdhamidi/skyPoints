{#
  Joins stg_redemptions to int_member_profile_final on the bare member_id
  (docs/01_Design_Specification.md §7). Because AUS/IND/USA local IDs
  overlap completely (all three use 1, 2, 3…), a member_id routinely matches
  more than one country — this is classified, never guessed:
    - RESOLVED  : exactly one country member_id matches
    - AMBIGUOUS : more than one country member_id matches
    - ORPHAN    : no country member_id matches
  Kept as a single global table, not split per country — the classification
  itself is not a per-country concept.
#}

with redemptions as (

    select * from {{ ref('stg_redemptions') }}

),

member_matches as (

    select distinct member_id, member_key, country_code
    from {{ ref('int_member_profile_final') }}

),

match_summary as (

    select
        member_id,
        count(*) as matching_country_count
    from member_matches
    group by member_id

),

resolved_match as (

    -- one row per member_id, only where exactly one country matched;
    -- max() here is a no-op tie-breaker since the group is a single row
    select
        member_id,
        max(member_key)   as member_key,
        max(country_code) as country_code
    from member_matches
    group by member_id
    having count(*) = 1

)

select
    r.txn_id,
    r.member_id,
    case
        when ms.matching_country_count = 1 then 'RESOLVED'
        when ms.matching_country_count > 1 then 'AMBIGUOUS'
        else 'ORPHAN'
    end                as match_status,
    rm.member_key,
    rm.country_code,
    r.txn_date,
    r.partner,
    r.miles_redeemed,
    r.status,
    r.feed_date,
    r.load_ts
from redemptions r
left join match_summary ms on r.member_id = ms.member_id
left join resolved_match rm on r.member_id = rm.member_id
