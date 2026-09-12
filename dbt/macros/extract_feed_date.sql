{#
  Extracts the run date from a source file name like "aus_member_20240115.csv"
  (the naming convention used by demo/generate_sample_feed.py). feed_date is the
  business date the extract represents (docs/01_Design_Specification.md §1),
  never wall-clock time.
#}
{% macro extract_feed_date(filename_col) %}
    to_date(regexp_substr({{ filename_col }}, '[0-9]{8}'), 'YYYYMMDD')
{% endmacro %}
