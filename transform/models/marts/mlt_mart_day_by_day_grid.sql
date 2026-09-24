{{
  config(
    alias=mlt_mart_table_name('mart_day_by_day_grid'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

WITH rate_shop AS (
  SELECT
    property_id,
    as_of_date,
    stay_date,
    ARRAY_AGG(
      STRUCT(
        dimension AS entity_key,
        dimension_label AS entity_label,
        {{ mlt_entity_role('dimension') }} AS entity_role,
        value AS rate,
        change AS rate_change
      )
      ORDER BY
        CASE
          WHEN dimension = '{{ var("subject_entity_key") }}' THEN 0
          WHEN dimension = 'avg_comp_set' THEN 1
          ELSE 2
        END,
        dimension_label
    ) AS rate_shop
  FROM {{ ref('stg_mlt_lighthouse_ota__snapshot_comp_set') }}
  GROUP BY property_id, as_of_date, stay_date
)

SELECT
  d.property_id,
  d.as_of_date,
  d.stay_date,
  d.stay_date_raw,
  d.lead_time_days,
  d.dow,
  d.month,
  d.is_weekend,
  d.ooo,
  d.rms_available,
  d.left_to_sell,
  d.on_the_books,
  d.occ_pct,
  d.adr,
  d.revenue_rev,
  d.revpar,
  d.group_otb,
  d.group_block,
  d.bar_otb,
  d.bar_8wk_rolling_avg,
  d.bi_forecast,
  d.market_demand,
  (d.market_demand * 100) - d.occ_pct AS market_demand_minus_occ,
  (SAFE_DIVIDE(d.bi_forecast, NULLIF(d.rms_available, 0)) * 100)
    - (d.market_demand * 100) AS forecast_minus_market,
  d.r28_avg,
  d.hurdle,
  d.optimal_bar,
  d.notes,
  d.pickup_rooms,
  d.pickup_adr_change,
  d.self_rate,
  d.comp_avg_rate,
  d.rate_index,
  d.self_rate - d.comp_avg_rate AS gap_to_comp_avg,
  d.date_range_start,
  d.date_range_end,
  d.pickup_from_date,
  d.exchange_rate_type,
  d.currency,
  d.exported_at,
  COALESCE(r.rate_shop, []) AS rate_shop,
  d.gcs_uri AS daily_gcs_uri,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM {{ ref('stg_mlt_lighthouse_ota__snapshot_daily') }} AS d
LEFT JOIN rate_shop AS r
  USING (property_id, as_of_date, stay_date)
