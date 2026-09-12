-- dbt singular test: fails (returns rows) if any member's country_code is
-- not a recognized value in the country reference seed. Directly targets the
-- inconsistent/non-standard country codes catalogued in
-- docs/05_Source_Data_Analysis.md §3 (e.g. 'PHIL', 'AU') — nothing in this
-- pipeline's own harmonization models should ever produce one, but this test
-- exists to catch it if a new source is added carelessly later.

select
    m.member_key,
    m.country_code
from {{ ref('stg_member_profile') }} m
left join {{ ref('country_reference') }} c
    on m.country_code = c.country_code
where c.country_code is null
