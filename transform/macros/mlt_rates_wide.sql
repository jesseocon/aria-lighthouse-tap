{% macro mlt_bq_column_key(expr) -%}
  {#- Same rule as table_column_key: [a-z0-9_], not starting with a digit. -#}
  {%- set slug = "regexp_replace(regexp_replace(lower(trim(cast(" ~ expr ~ " as string))), r'[^a-z0-9]+', '_'), r'^_+|_+$', '')" -%}
  if(regexp_contains({{ slug }}, r'^[0-9]|^$'), concat('_', {{ slug }}), {{ slug }})
{%- endmacro %}

{% macro mlt_rates_competitor_columns() %}
  {#- Distinct competitor columns from the long bronze table. Empty during parse. -#}
  {% set columns = [] %}
  {% if execute %}
    {% set sql %}
      select
        {{ mlt_bq_column_key('competitor_key') }} as competitor_key,
        any_value(competitor) as competitor
      from {{ source('mlt_lighthouse_ota', 'rates') }}
      where nullif(trim(cast(competitor_key as string)), '') is not null
      group by 1
      order by 1
    {% endset %}
    {% set result = run_query(sql) %}
    {% if result is not none %}
      {% for row in result.rows %}
        {% do columns.append({'key': row[0], 'name': row[1]}) %}
      {% endfor %}
    {% endif %}
  {% endif %}
  {{ return(columns) }}
{% endmacro %}

{% macro mlt_sql_literal(value) -%}
  '{{ (value | string) | replace("'", "''") }}'
{%- endmacro %}

{% macro mlt_bq_ident(value) -%}
  `{{ (value | string) | replace('`', '') }}`
{%- endmacro %}

{% macro mlt_rates_competitor_names_sql(columns) -%}
  {%- set pairs = [] -%}
  {%- for column in columns -%}
    {%- set key = (column.key | string) | replace('\\', '\\\\') | replace('"', '\\"') -%}
    {%- set name = (column.name | string) | replace('\\', '\\\\') | replace('"', '\\"') -%}
    {%- do pairs.append('"' ~ key ~ '": "' ~ name ~ '"') -%}
  {%- endfor -%}
  {{ mlt_sql_literal('{' ~ (pairs | join(', ')) ~ '}') }}
{%- endmacro %}

{% macro mlt_rates_wide_metric(column_key, source_column, alias_suffix) -%}
  max(
    if(
      {{ mlt_bq_column_key('competitor_key') }} = {{ mlt_sql_literal(column_key) }},
      {{ source_column }},
      null
    )
  ) as {{ mlt_bq_ident(column_key ~ alias_suffix) }}
{%- endmacro %}
