{{ config(materialized='table', tags=['country_tables']) }}

{#
  Thin wrapper model whose only purpose is to trigger generate_country_tables()
  (macros/generate_country_tables.sql) as part of `dbt run --select marts` —
  the actual per-country tables (MARTS.TABLE_<COUNTRY>) are created as a side
  effect of that macro, not by this model's own SELECT. This model's own
  output is just a small audit row recording when the split last ran.
  See docs/01_Design_Specification.md §6.5, docs/03_Technical_Build_Plan.md §4
  (dbt_run_marts task).
#}
{{ generate_country_tables() }}

select
    current_timestamp() as generated_at,
    (select count(*) from {{ ref('country_reference') }}) as country_count
