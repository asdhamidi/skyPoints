{#
  Parses USA.csv's concatenated, undelimited digit-string dates
  (docs/01_Design_Specification.md §4). An 8-digit value has only one valid
  MM/DD/YYYY split. A 7-digit value has two candidate splits (month_len=1 or 2);
  this parses it ONLY when exactly one split is calendar-valid. A value where
  both splits are valid (e.g. '1052022' -> Jan 5 or Oct 5) is genuinely
  ambiguous and resolves to NULL — never a guess. A value where neither split
  is valid also resolves to NULL.
#}
{% macro parse_usa_date(date_col) %}
    case
        when length({{ date_col }}) = 8 then
            try_to_date(
                substr({{ date_col }}, 1, 2) || '/' || substr({{ date_col }}, 3, 2) || '/' || substr({{ date_col }}, 5, 4),
                'MM/DD/YYYY'
            )
        when length({{ date_col }}) = 7 then
            case
                when
                    (try_to_date(substr({{ date_col }}, 1, 1) || '/' || substr({{ date_col }}, 2, 2) || '/' || substr({{ date_col }}, 4, 4), 'MM/DD/YYYY') is not null)
                    <>
                    (try_to_date(substr({{ date_col }}, 1, 2) || '/' || substr({{ date_col }}, 3, 1) || '/' || substr({{ date_col }}, 4, 4), 'MM/DD/YYYY') is not null)
                then
                    coalesce(
                        try_to_date(substr({{ date_col }}, 1, 1) || '/' || substr({{ date_col }}, 2, 2) || '/' || substr({{ date_col }}, 4, 4), 'MM/DD/YYYY'),
                        try_to_date(substr({{ date_col }}, 1, 2) || '/' || substr({{ date_col }}, 3, 1) || '/' || substr({{ date_col }}, 4, 4), 'MM/DD/YYYY')
                    )
                else null
            end
        else null
    end
{% endmacro %}
