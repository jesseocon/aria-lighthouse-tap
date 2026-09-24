{{
  config(
    alias=mlt_stream_table_name('snapshot_daily'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

WITH raw AS (
  SELECT *
  FROM {{ source('mlt_lighthouse_ota', 'snapshot_daily') }}
),

parsed AS (
  SELECT
    NULLIF({{ mlt_as_string('_hotel_id') }}, '') AS hotel_id,
    {{ mlt_parse_as_of_date('as_of_date') }} AS as_of_date,
    {{ mlt_parse_stay_date('as_of_date_date') }} AS stay_date,
    as_of_date_date AS stay_date_raw,
    DATE_DIFF(
      {{ mlt_parse_stay_date('as_of_date_date') }},
      {{ mlt_parse_as_of_date('as_of_date') }},
      DAY
    ) AS lead_time_days,
    FORMAT_DATE(
      '%a',
      {{ mlt_parse_stay_date('as_of_date_date') }}
    ) AS dow,
    FORMAT_DATE(
      '%Y-%m',
      {{ mlt_parse_stay_date('as_of_date_date') }}
    ) AS month,
    IF(
      FORMAT_DATE('%a', {{ mlt_parse_stay_date('as_of_date_date') }}) IN ('Sat', 'Sun'),
      1,
      0
    ) AS is_weekend,
    {{ mlt_parse_fraction_left('on_the_books_ooo_rms_available') }} AS ooo,
    {{ mlt_parse_fraction_right('on_the_books_ooo_rms_available') }} AS rms_available,
    SAFE_CAST(NULLIF({{ mlt_as_string('on_the_books_left_to_sell') }}, '') AS INT64) AS left_to_sell,
    SAFE_CAST(NULLIF({{ mlt_as_string('on_the_books') }}, '') AS INT64) AS on_the_books,
    {{ mlt_parse_percent('on_the_books_total_occ_percentage') }} AS occ_pct,
    {{ mlt_parse_currency('on_the_books_adr') }} AS adr,
    {{ mlt_parse_currency('revenue_rev') }} AS revenue_rev,
    {{ mlt_parse_currency('revenue_revpar') }} AS revpar,
    {{ mlt_parse_fraction_left('group_otb_block') }} AS group_otb,
    {{ mlt_parse_fraction_right('group_otb_block') }} AS group_block,
    CASE
      WHEN STRPOS({{ mlt_as_string('bar_based_stats_otb') }}, '/') > 0 THEN
        {{ mlt_parse_fraction_left('bar_based_stats_otb') }}
      ELSE SAFE_CAST(NULLIF(REGEXP_REPLACE({{ mlt_as_string('bar_based_stats_otb') }}, r'[$,%]', ''), '') AS INT64)
    END AS bar_otb,
    {{ mlt_parse_metric_num('bar_based_stats_8_week_rolling_avg', true) }} AS bar_8wk_rolling_avg,
    {{ mlt_parse_metric_num('pricing_and_forecast_rms_forecast', true) }} AS bi_forecast,
    {{ mlt_parse_percent('pricing_and_forecast_market_demand') }} AS market_demand,
    {{ mlt_parse_metric_num('pricing_and_forecast_r28_avg', true) }} AS r28_avg,
    {{ mlt_parse_currency('pricing_and_forecast_hurdle', true) }} AS hurdle,
    {{ mlt_parse_metric_num('pricing_and_forecast_optimal_bar', true) }} AS optimal_bar,
    NULLIF({{ mlt_as_string('notes') }}, '') AS notes,
    {{ mlt_parse_metric_num('pickup_from_rooms') }} AS pickup_rooms,
    {{ mlt_parse_metric_num('pickup_from_adr_change') }} AS pickup_adr_change,
    {{ mlt_parse_metric_num(mlt_rate_shop_col_ref(var('subject_entity_key'), 'rate')) }} AS self_rate,
    {{ mlt_parse_metric_num(mlt_rate_shop_col_ref('avg_comp_set', 'rate')) }} AS comp_avg_rate,
    SAFE_DIVIDE(
      {{ mlt_parse_metric_num(mlt_rate_shop_col_ref(var('subject_entity_key'), 'rate')) }},
      NULLIF({{ mlt_parse_metric_num(mlt_rate_shop_col_ref('avg_comp_set', 'rate')) }}, 0)
    ) AS rate_index,
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
  FROM raw
)

SELECT
  hotel_id,
  as_of_date,
  stay_date,
  stay_date_raw,
  lead_time_days,
  dow,
  month,
  is_weekend,
  ooo,
  rms_available,
  left_to_sell,
  on_the_books,
  occ_pct,
  adr,
  revenue_rev,
  revpar,
  group_otb,
  group_block,
  bar_otb,
  bar_8wk_rolling_avg,
  bi_forecast,
  market_demand,
  r28_avg,
  hurdle,
  optimal_bar,
  notes,
  pickup_rooms,
  pickup_adr_change,
  self_rate,
  comp_avg_rate,
  rate_index,
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
FROM parsed
WHERE stay_date IS NOT NULL
  AND as_of_date IS NOT NULL
  AND lead_time_days >= 0
