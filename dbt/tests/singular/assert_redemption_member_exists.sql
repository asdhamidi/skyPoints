-- dbt singular test: fails (returns rows) if a redemption classified
-- RESOLVED doesn't actually correspond to a real member_key in
-- int_member_profile_final. This checks the join/classification logic
-- itself (marts/redemptions.sql) — it is NOT a rule against ORPHAN or
-- AMBIGUOUS rows existing, which are expected outcomes given the source
-- ID overlap (docs/01_Design_Specification.md §7, §9), not data defects.

select r.txn_id, r.member_id, r.match_status, r.member_key
from {{ ref('redemptions') }} r
left join {{ ref('int_member_profile_final') }} m
    on r.member_key = m.member_key
where r.match_status = 'RESOLVED'
  and m.member_key is null
