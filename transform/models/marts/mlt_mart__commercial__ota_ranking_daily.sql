{{
  config(
    alias=mlt_mart_table_name('commercial__ota_ranking_daily'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

{#- Subject hotel's OTA search rank per stay date, as seen on each capture day,
    against the comp set. Rank 0 from Lighthouse means "not ranked": it is null here. -#}

WITH cells AS (
  SELECT
    *,
    NULLIF(ranking, 0) AS rank_or_null,
    NULLIF(price_value, 0) AS price_or_null
  FROM {{ ref('stg_mlt_lighthouse_ota__ota_ranking_daily') }}
)

SELECT
  '{{ var("property_id") }}' AS property_id,
  as_of_date,
  stay_date,
  DATE_DIFF(stay_date, as_of_date, DAY) AS lead_time_days,
  ota,
  ANY_VALUE(IF(is_subject_hotel, rank_or_null, NULL)) AS subject_ranking,
  ANY_VALUE(IF(is_subject_hotel, available_hotels, NULL)) AS ranked_among,
  ANY_VALUE(IF(is_subject_hotel, message, NULL)) AS subject_message,
  LOGICAL_OR(is_subject_hotel AND rank_or_null IS NOT NULL) AS subject_in_results,
  LOGICAL_OR(is_subject_hotel AND message = 'ranking.soldout') AS subject_sold_out,
  ANY_VALUE(IF(is_subject_hotel, price_or_null, NULL)) AS subject_price,
  ANY_VALUE(IF(is_subject_hotel, currency, NULL)) AS currency,
  COUNTIF(NOT is_subject_hotel AND rank_or_null IS NOT NULL) AS compset_ranked_hotels,
  MIN(IF(NOT is_subject_hotel, rank_or_null, NULL)) AS compset_best_ranking,
  APPROX_QUANTILES(IF(NOT is_subject_hotel, price_or_null, NULL), 2 IGNORE NULLS)[SAFE_OFFSET(1)] AS compset_median_price,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM cells
GROUP BY as_of_date, stay_date, ota
