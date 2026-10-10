{% macro mlt_dataset(layer) -%}
  {{ var('bq_project') }}.{{ layer }}_{{ var('org_id') }}
{%- endmacro %}

{% macro mlt_bronze_snapshot_daily_table() -%}
  {{ var('source') }}__snapshot_daily_hotel_{{ var('hotel_id') }}
{%- endmacro %}

{% macro mlt_latest_snapshot_rows() -%}
  {#- Re-scraped as-of dates can land more than once; keep the newest extract per key. -#}
  SELECT *
  FROM {{ source('mlt_lighthouse_ota', 'snapshot_daily') }}
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY as_of_date, stay_date
    ORDER BY _sdc_extracted_at DESC, _sdc_received_at DESC, _sdc_batched_at DESC
  ) = 1
{%- endmacro %}

{% macro mlt_bronze_parity_list_table() -%}
  {{ var('source') }}__parity_list_hotel_{{ var('hotel_id') }}
{%- endmacro %}

{% macro mlt_bronze_budget_table() -%}
  {{ var('source') }}__budget_hotel_{{ var('hotel_id') }}
{%- endmacro %}

{% macro mlt_bronze_forecast_table() -%}
  {{ var('source') }}__forecast_hotel_{{ var('hotel_id') }}
{%- endmacro %}

{% macro mlt_stg_monthly_hierarchical(source_relation) -%}
  SELECT
    '{{ var("property_id") }}' AS property_id,
    raw.* EXCEPT (run_timestamp, stay_date, row_level, parent_date_key),
    CAST(raw.stay_date AS DATE) AS stay_date,
    TIMESTAMP(raw.run_timestamp) AS run_timestamp,
    SAFE_CAST(raw.row_level AS INT64) AS row_level,
    SAFE_CAST(raw.parent_date_key AS DATE) AS parent_date_key
  FROM {{ source_relation }} AS raw
{%- endmacro %}

{% macro mlt_parse_parity_run_timestamp(column_expr) -%}
  COALESCE(
    SAFE.PARSE_TIMESTAMP(
      '%Y-%m-%dT%H:%M:%E*S%Ez',
      NULLIF({{ mlt_as_string(column_expr) }}, '')
    ),
    SAFE.PARSE_TIMESTAMP(
      '%Y-%m-%dT%H:%M:%E*S%z',
      NULLIF({{ mlt_as_string(column_expr) }}, '')
    ),
    SAFE.PARSE_TIMESTAMP(
      '%Y-%m-%dT%H:%M:%E*S',
      NULLIF({{ mlt_as_string(column_expr) }}, '')
    )
  )
{%- endmacro %}

{% macro mlt_parity_channel_label(channel_key) -%}
  JSON_VALUE(
    PARSE_JSON({{ mlt_as_string('_parity_entity_labels') }}),
    '$.{{ channel_key }}'
  )
{%- endmacro %}

{% macro mlt_stream_table_name(stream) -%}
  {{ var('source') }}__{{ stream }}_{{ var('property_id') }}
{%- endmacro %}

{% macro mlt_table_fqn(layer, stream) -%}
  `{{ mlt_dataset(layer) }}.{{ mlt_stream_table_name(stream) }}`
{%- endmacro %}

{% macro mlt_mart_table_name(suffix) -%}
  mlt_mart__{{ suffix }}_{{ var('property_id') }}
{%- endmacro %}

{% macro mlt_mart_fqn(mart_base) -%}
  `{{ mlt_dataset('gold') }}.{{ mlt_mart_table_name(mart_base) }}`
{%- endmacro %}

{% macro mlt_slug_label(label) -%}
  {%- set slug = modules.re.sub('[^a-z0-9]+', '_', (label | string).strip().lower()).strip('_') -%}
  {%- if slug and slug[0].isdigit() -%}
    {%- set slug = '_' ~ slug -%}
  {%- endif -%}
  {{ return(slug) }}
{%- endmacro %}

{% macro mlt_subject_entity_key() -%}
  {#- The rate-shop column for this hotel. The scrape writes it; the property name is the fallback. -#}
  {%- if not execute -%}
    {{ return(var('subject_entity_key', 'subject')) }}
  {%- endif -%}
  {%- set relation = source('mlt_lighthouse_ota', 'snapshot_daily') -%}
  {%- set columns = adapter.get_columns_in_relation(relation) | map(attribute='name') | map('lower') | list -%}
  {%- if '_subject_entity_key' in columns -%}
    {%- set found = run_query('select any_value(_subject_entity_key) from ' ~ relation) -%}
    {%- if found and found.rows and found.rows[0][0] -%}
      {{ return(found.rows[0][0]) }}
    {%- endif -%}
  {%- endif -%}
  {%- if '_property_name' in columns -%}
    {%- set found = run_query('select any_value(_property_name) from ' ~ relation) -%}
    {%- if found and found.rows and found.rows[0][0] -%}
      {{ return(mlt_slug_label(found.rows[0][0])) }}
    {%- endif -%}
  {%- endif -%}
  {{ exceptions.raise_compiler_error('Strategy snapshot has no subject hotel. Re-scrape so the export can record it.') }}
{%- endmacro %}

{% macro mlt_entity_role(dimension) -%}
  CASE
    WHEN {{ dimension }} = 'avg_comp_set' THEN 'comp_avg'
    WHEN {{ dimension }} = '{{ mlt_subject_entity_key() }}' THEN 'subject'
    ELSE 'comp'
  END
{%- endmacro %}

{% macro mlt_pivot_parent_group_slug() -%}
  {#- Rate-shop column prefix. The scrape writes it on each snapshot row. -#}
  {%- if not execute -%}
    {{ return(var('pivot_parent_group_slug')) }}
  {%- endif -%}
  {%- set relation = source('mlt_lighthouse_ota', 'snapshot_daily') -%}
  {%- set columns = adapter.get_columns_in_relation(relation) | map(attribute='name') | map('lower') | list -%}
  {%- if '_pivot_parent_group_slug' not in columns -%}
    {{ exceptions.raise_compiler_error('Strategy snapshot has no rate-shop group. Re-scrape so the export can record it.') }}
  {%- endif -%}
  {%- set found = run_query('select any_value(_pivot_parent_group_slug) from ' ~ relation) -%}
  {%- if not found or not found.rows or not found.rows[0][0] -%}
    {{ exceptions.raise_compiler_error('Strategy snapshot has no rate-shop group. Re-scrape so the export can record it.') }}
  {%- endif -%}
  {{ return(found.rows[0][0]) }}
{%- endmacro %}

{% macro mlt_rate_shop_dimensions() -%}
  {#- Comp-set column keys, taken from the scraped rate-shop columns. -#}
  {%- if not execute -%}
    {{ return(var('rate_shop_dimensions')) }}
  {%- endif -%}
  {%- set slug = mlt_pivot_parent_group_slug() -%}
  {%- set relation = source('mlt_lighthouse_ota', 'snapshot_daily') -%}
  {%- set columns = adapter.get_columns_in_relation(relation) | map(attribute='name') | map('lower') | list -%}
  {%- set prefix = slug ~ '_' -%}
  {%- set dims = [] -%}
  {%- for name in columns -%}
    {%- if name.startswith(prefix) and name.endswith('_rate') -%}
      {%- set dim = modules.re.sub('_rate$', '', modules.re.sub('^' ~ modules.re.escape(prefix), '', name)) -%}
      {%- if dim -%}
        {%- do dims.append(dim) -%}
      {%- endif -%}
    {%- endif -%}
  {%- endfor -%}
  {%- if dims | length == 0 -%}
    {{ exceptions.raise_compiler_error('Strategy snapshot has no rate-shop columns. Re-scrape so the export can record them.') }}
  {%- endif -%}
  {{ return(dims) }}
{%- endmacro %}

{% macro mlt_rate_shop_col_ref(dimension, metric) -%}
  `{{ mlt_pivot_parent_group_slug() }}_{{ dimension }}_{{ metric }}`
{%- endmacro %}

{% macro mlt_as_string(column_expr) -%}
  TRIM(CAST({{ column_expr }} AS STRING))
{%- endmacro %}

{% macro mlt_parse_stay_date(raw_column) -%}
  COALESCE(
    SAFE_CAST({{ raw_column }} AS DATE),
    SAFE.PARSE_DATE(
      '%m/%d/%y',
      REGEXP_REPLACE({{ mlt_as_string(raw_column) }}, r' [A-Za-z]+$', '')
    ),
    SAFE.PARSE_DATE(
      '%m/%d/%Y',
      REGEXP_REPLACE({{ mlt_as_string(raw_column) }}, r' [A-Za-z]+$', '')
    )
  )
{%- endmacro %}

{% macro mlt_parse_context_date(raw_column) -%}
  COALESCE(
    SAFE_CAST({{ raw_column }} AS DATE),
    SAFE.PARSE_DATE('%m/%d/%Y', NULLIF({{ mlt_as_string(raw_column) }}, '')),
    SAFE.PARSE_DATE('%Y-%m-%d', NULLIF({{ mlt_as_string(raw_column) }}, ''))
  )
{%- endmacro %}

{% macro mlt_parse_as_of_date(column_expr) -%}
  COALESCE(
    SAFE_CAST({{ column_expr }} AS DATE),
    SAFE.PARSE_DATE('%Y-%m-%d', NULLIF({{ mlt_as_string(column_expr) }}, ''))
  )
{%- endmacro %}

{% macro mlt_parse_metric_num(column_expr, zero_as_empty=false) -%}
  CASE
    WHEN {{ column_expr }} IS NULL THEN NULL
    WHEN NULLIF({{ mlt_as_string(column_expr) }}, '') IS NULL THEN NULL
    WHEN UPPER({{ mlt_as_string(column_expr) }}) = 'X' THEN NULL
    WHEN NOT REGEXP_CONTAINS({{ mlt_as_string(column_expr) }}, r'[-0-9.]') THEN NULL
    ELSE
      IF(
        {{ zero_as_empty }},
        NULLIF(SAFE_CAST(REGEXP_REPLACE({{ mlt_as_string(column_expr) }}, r'[$,%]', '') AS FLOAT64), 0),
        SAFE_CAST(REGEXP_REPLACE({{ mlt_as_string(column_expr) }}, r'[$,%]', '') AS FLOAT64)
      )
  END
{%- endmacro %}

{% macro mlt_parse_currency(column_expr, zero_as_empty=false) -%}
  CASE
    WHEN {{ column_expr }} IS NULL THEN NULL
    WHEN NULLIF({{ mlt_as_string(column_expr) }}, '') IS NULL THEN NULL
    WHEN UPPER({{ mlt_as_string(column_expr) }}) = 'X' THEN NULL
    ELSE
      IF(
        {{ zero_as_empty }},
        NULLIF(SAFE_CAST(REGEXP_REPLACE({{ mlt_as_string(column_expr) }}, r'[$,]', '') AS FLOAT64), 0),
        SAFE_CAST(REGEXP_REPLACE({{ mlt_as_string(column_expr) }}, r'[$,]', '') AS FLOAT64)
      )
  END
{%- endmacro %}

{% macro mlt_parse_percent(column_expr) -%}
  CASE
    WHEN {{ column_expr }} IS NULL THEN NULL
    WHEN NULLIF({{ mlt_as_string(column_expr) }}, '') IS NULL THEN NULL
    ELSE SAFE_CAST(REGEXP_EXTRACT({{ mlt_as_string(column_expr) }}, r'^(\d+(?:\.\d+)?)') AS FLOAT64) / 100
  END
{%- endmacro %}

{% macro mlt_parse_fraction_left(column_expr) -%}
  SAFE_CAST(
    NULLIF(
      REGEXP_REPLACE(
        IF(
          STRPOS({{ mlt_as_string(column_expr) }}, '/') > 0,
          SPLIT({{ mlt_as_string(column_expr) }}, '/')[SAFE_OFFSET(0)],
          {{ mlt_as_string(column_expr) }}
        ),
        r'[$,%]',
        ''
      ),
      ''
    ) AS INT64
  )
{%- endmacro %}

{% macro mlt_parse_fraction_right(column_expr) -%}
  SAFE_CAST(
    NULLIF(
      REGEXP_REPLACE(
        IF(
          STRPOS({{ mlt_as_string(column_expr) }}, '/') > 0,
          SPLIT({{ mlt_as_string(column_expr) }}, '/')[SAFE_OFFSET(1)],
          ''
        ),
        r'[$,%]',
        ''
      ),
      ''
    ) AS INT64
  )
{%- endmacro %}
