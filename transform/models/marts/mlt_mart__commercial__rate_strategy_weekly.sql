{{
  config(
    alias=mlt_mart_table_name('commercial__rate_strategy_weekly'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

{#- Per week and strategy (member rate, mobile, non-refundable, LOS, meal plan...):
    what the subject does against how many competitors use it, and how deeply.
    value is a fraction of the base rate (-0.02 = 2% off) unless is_absolute, when it
    is an amount. Medians are taken over competitors that offer the strategy. -#}

WITH discounts AS (
  SELECT
    *,
    COALESCE(message, '') NOT IN ('rates.notoffered', 'rates.noncomputable') AS is_offered
  FROM {{ ref('stg_mlt_lighthouse_ota__rate_strategy_discounts') }}
),

subject_bar AS (
  SELECT snapshot_week, MIN(rate) AS subject_bar_rate, ANY_VALUE(currency) AS currency
  FROM {{ ref('stg_mlt_lighthouse_ota__rate_strategy_base_rates') }}
  WHERE is_subject_hotel AND is_bar
  GROUP BY snapshot_week
)

SELECT
  '{{ var("property_id") }}' AS property_id,
  d.snapshot_week,
  d.rs_type,
  d.rs_subtype,
  ANY_VALUE(d.rs_subtype_label) AS rs_subtype_label,
  LOGICAL_OR(d.is_subject_hotel AND d.is_offered) AS subject_offers,
  ANY_VALUE(IF(d.is_subject_hotel AND d.is_offered, d.value, NULL)) AS subject_value,
  ANY_VALUE(IF(d.is_subject_hotel, d.is_absolute, NULL)) AS subject_is_absolute,
  ANY_VALUE(IF(d.is_subject_hotel AND d.is_offered, d.discounted_price, NULL)) AS subject_price,
  ANY_VALUE(IF(d.is_subject_hotel, d.frequency_weekday, NULL)) AS subject_frequency_weekday,
  ANY_VALUE(IF(d.is_subject_hotel, d.frequency_weekend, NULL)) AS subject_frequency_weekend,
  COUNTIF(NOT d.is_subject_hotel) AS compset_hotels,
  COUNTIF(NOT d.is_subject_hotel AND d.is_offered) AS compset_hotels_offering,
  SAFE_DIVIDE(COUNTIF(NOT d.is_subject_hotel AND d.is_offered), COUNTIF(NOT d.is_subject_hotel)) AS compset_share_offering,
  APPROX_QUANTILES(IF(NOT d.is_subject_hotel AND d.is_offered, d.value, NULL), 2 IGNORE NULLS)[SAFE_OFFSET(1)]
    AS compset_median_value,
  ANY_VALUE(b.subject_bar_rate) AS subject_bar_rate,
  ANY_VALUE(b.currency) AS currency,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM discounts AS d
LEFT JOIN subject_bar AS b USING (snapshot_week)
GROUP BY d.snapshot_week, d.rs_type, d.rs_subtype
