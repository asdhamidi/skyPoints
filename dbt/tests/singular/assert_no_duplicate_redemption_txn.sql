-- dbt singular test: fails (returns rows) if txn_id is not unique across
-- the flattened redemption feed.

select txn_id, count(*) as occurrences
from {{ ref('stg_redemptions') }}
group by txn_id
having count(*) > 1
