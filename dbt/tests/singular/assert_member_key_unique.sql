-- dbt singular test: fails (returns rows) if member_key is not unique in
-- stg_member_profile. Per docs/01_Design_Specification.md §3: member_key —
-- not member_name (docs/05 §3) or the raw source-local ID (docs/01 §3) — is
-- the enforced uniqueness key.

select
    member_key,
    count(*) as occurrences
from {{ ref('stg_member_profile') }}
group by member_key
having count(*) > 1
