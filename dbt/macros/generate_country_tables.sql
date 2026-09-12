{#
  Issues one CREATE OR REPLACE TABLE MARTS.TABLE_<COUNTRY> per row of the
  country_reference seed (docs/01_Design_Specification.md §6.5). Adding a
  country is a seed-file edit, not a new model.

  ref() calls are hoisted OUTSIDE the {% if execute %} guard so dbt's static
  parser always sees them (and registers int_member_profile_final and
  country_reference as upstream dependencies) even during a dry parse/compile
  pass, when execute is False and the run_query side effects below don't run.
#}
{% macro generate_country_tables() %}

    {%- set profile_relation = ref('int_member_profile_final') -%}
    {%- set country_ref_relation = ref('country_reference') -%}

    {% if execute %}
        {% set countries_query %}
            select country_code from {{ country_ref_relation }}
        {% endset %}
        {% set countries = run_query(countries_query).columns[0].values() %}

        {% for country in countries %}
            {% set create_sql %}
                create or replace table {{ target.database }}.MARTS.TABLE_{{ country }} as
                select * from {{ profile_relation }}
                where country_code = '{{ country }}'
            {% endset %}
            {% do run_query(create_sql) %}
            {% do log("generate_country_tables: created/replaced MARTS.TABLE_" ~ country, info=true) %}
        {% endfor %}
    {% endif %}

{% endmacro %}
