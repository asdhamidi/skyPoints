{#
  Stale_Member_Flag (docs/01_Design_Specification.md §6.2): TRUE when more
  than 90 days have passed between last_flight_date and feed_date. NULL where
  last_flight_date is NULL, rather than defaulting to TRUE or FALSE — absence
  of a flight date is not evidence either way.
#}
{% macro is_stale_member(last_flight_date_col, asof_col) %}
    case
        when {{ last_flight_date_col }} is null then null
        else datediff(day, {{ last_flight_date_col }}, {{ asof_col }}) > 90
    end
{% endmacro %}
