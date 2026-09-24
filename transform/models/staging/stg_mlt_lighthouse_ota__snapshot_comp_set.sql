{{
  config(
    alias=mlt_stream_table_name('snapshot_comp_set'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

WITH raw AS (
  SELECT *
  FROM {{ source('mlt_lighthouse_ota', 'snapshot_daily') }}
),

expanded AS (
  SELECT
    raw.* EXCEPT (as_of_date),
    {{ mlt_parse_stay_date('as_of_date_date') }} AS stay_date,
    {{ mlt_parse_as_of_date('as_of_date') }} AS as_of_date
  FROM raw
),

rate_shop_rows AS (
  {% for dimension in var('rate_shop_dimensions') %}
  SELECT
    NULLIF({{ mlt_as_string('_hotel_id') }}, '') AS hotel_id,
    as_of_date,
    stay_date,
    as_of_date_date AS stay_date_raw,
    DATE_DIFF(stay_date, as_of_date, DAY) AS lead_time_days,
    NULLIF({{ mlt_as_string('_pivot_parent_group') }}, '') AS dimension_group,
    NULLIF({{ mlt_as_string('_pivot_parent_group_slug') }}, '') AS dimension_group_slug,
    '{{ dimension }}' AS dimension,
    JSON_VALUE(PARSE_JSON(_pivot_entity_labels), '$.{{ dimension }}') AS dimension_label,
    {{ mlt_parse_metric_num(mlt_rate_shop_col_ref(dimension, 'rate')) }} AS value,
    {{ mlt_parse_metric_num(mlt_rate_shop_col_ref(dimension, 'change')) }} AS change,
    {{ mlt_parse_context_date('_date_range_start') }} AS date_range_start,
    {{ mlt_parse_context_date('_date_range_end') }} AS date_range_end,
    {{ mlt_parse_context_date('_pickup_from_date') }} AS pickup_from_date,
    NULLIF({{ mlt_as_string('_exchange_rate_type') }}, '') AS exchange_rate_type,
    NULLIF({{ mlt_as_string('_currency') }}, '') AS currency,
    SAFE.PARSE_TIMESTAMP(
      '%Y-%m-%dT%H:%M:%E*S',
      NULLIF({{ mlt_as_string('_exported_at') }}, '')
    ) AS exported_at,
    CAST(NULL AS STRING) AS source_file,
    CAST(NULL AS STRING) AS gcs_uri,
    '{{ var("property_id") }}' AS property_id
  FROM expanded
  {% if not loop.last %}
  UNION ALL
  {% endif %}
  {% endfor %}
)

SELECT
  hotel_id,
  as_of_date,
  stay_date,
  stay_date_raw,
  lead_time_days,
  dimension_group,
  dimension_group_slug,
  dimension,
  dimension_label,
  value,
  change,
  date_range_start,
  date_range_end,
  pickup_from_date,
  exchange_rate_type,
  currency,
  exported_at,
  source_file,
  gcs_uri,
  property_id,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM rate_shop_rows
WHERE stay_date IS NOT NULL
  AND as_of_date IS NOT NULL
  AND lead_time_days >= 0
