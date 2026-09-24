{{
  config(
    alias=mlt_mart_table_name('mart_rate_shop_daily'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

SELECT
  property_id,
  as_of_date,
  stay_date,
  lead_time_days,
  dimension AS entity_key,
  dimension_label AS entity_label,
  {{ mlt_entity_role('dimension') }} AS entity_role,
  value AS rate,
  change AS rate_change,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM {{ ref('stg_mlt_lighthouse_ota__snapshot_comp_set') }}
