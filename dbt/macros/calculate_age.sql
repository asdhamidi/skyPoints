{#
  Age as of feed_date (docs/01_Design_Specification.md §6.1) — the business
  date the extract represents, not wall-clock time, so re-running the same
  day's data later doesn't change the result. NULL where dob is NULL (every
  USA row, docs/01 §2 — USA.csv carries no DOB column at all).
#}
{% macro calculate_age(dob_col, asof_col) %}
    case
        when {{ dob_col }} is null then null
        else
            datediff(year, {{ dob_col }}, {{ asof_col }})
            - iff(
                to_char({{ asof_col }}, 'MMDD') < to_char({{ dob_col }}, 'MMDD'),
                1,
                0
              )
    end
{% endmacro %}
