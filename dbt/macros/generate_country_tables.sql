{#
  Issues one CREATE TABLE IF NOT EXISTS + MERGE per row of the
  country_reference seed (docs/01_Design_Specification.md §6.5, §11). Adding a
  country is a seed-file edit, not a new model.

  MERGE instead of the earlier CREATE OR REPLACE: a full rebuild re-writes
  every country table's entire contents on every run regardless of how few
  members actually changed. MERGE only touches member_keys that are new or
  whose attributes changed, which is what keeps this affordable as the
  population grows (docs/01 §11) — a full-refresh's cost scales with total
  population on every single run; MERGE's scales with what's actually new
  today, on every run except the very first.

  ref() calls are hoisted OUTSIDE the {% if execute %} guard so dbt's static
  parser always sees them (and registers int_member_profile_final and
  country_reference as upstream dependencies) even during a dry parse/compile
  pass, when execute is False and the run_query side effects below don't run.
#}
{% macro generate_country_tables() %}

    {%- set profile_relation = ref('int_member_profile_final') -%}
    {%- set country_ref_relation = ref('country_reference') -%}

    {%- set profile_columns = [
        'member_id', 'member_name', 'dob', 'enrollment_date', 'last_flight_date',
        'tier_code', 'agent_name', 'state', 'country_code', 'post_code', 'is_active',
        'membership_type', 'age', 'stale_member_flag', 'source_system', 'feed_date', 'load_ts'
    ] -%}

    {% if execute %}
        {% set countries_query %}
            select country_code from {{ country_ref_relation }}
        {% endset %}
        {% set countries = run_query(countries_query).columns[0].values() %}

        {% for country in countries %}
            {% set target_table = target.database ~ ".MARTS.TABLE_" ~ country %}

            {% set create_if_missing_sql %}
                create table if not exists {{ target_table }} like {{ profile_relation }}
            {% endset %}
            {% do run_query(create_if_missing_sql) %}

            {% set merge_sql %}
                merge into {{ target_table }} as tgt
                using (
                    select * from {{ profile_relation }} where country_code = '{{ country }}'
                ) as src
                on tgt.member_key = src.member_key
                when matched then update set
                    {% for col in profile_columns %}
                    {{ col }} = src.{{ col }}{{ "," if not loop.last }}
                    {% endfor %}
                when not matched then insert (member_key, {{ profile_columns | join(', ') }})
                values (src.member_key, {% for col in profile_columns %}src.{{ col }}{{ ", " if not loop.last }}{% endfor %})
            {% endset %}
            {% do run_query(merge_sql) %}
            {% do log("generate_country_tables: merged MARTS.TABLE_" ~ country, info=true) %}
        {% endfor %}
    {% endif %}

{% endmacro %}
