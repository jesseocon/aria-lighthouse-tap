{{
  config(
    alias=mlt_mart_table_name('commercial__ota_reputation'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

{#- Subject hotel vs comp set, per OTA and period (weekly and monthly).
    Rankings mean different things per OTA: Booking.com and Tripadvisor rank within
    the comp set, Expedia within the whole market, so ranked_among travels with the rank.
    Review scores are out of 10 (Booking.com, Expedia) or 5 (Tripadvisor). -#}

WITH summaries AS (
  SELECT
    *,
    MAX(IF(is_subject_hotel, review_score, NULL)) OVER (PARTITION BY granularity, period, ota) AS subject_score
  FROM {{ ref('stg_mlt_lighthouse_ota__ota_ranking_summary') }}
  WHERE message IS NULL
)

SELECT
  '{{ var("property_id") }}' AS property_id,
  granularity,
  period,
  MIN(period_start) AS period_start,
  ota,
  IF(ota = 'tripadvisor', 5, 10) AS review_scale,
  ANY_VALUE(IF(is_subject_hotel, NULLIF(ranking, 0), NULL)) AS subject_ranking,
  ANY_VALUE(IF(is_subject_hotel, available_hotels, NULL)) AS ranked_among,
  ROUND(ANY_VALUE(IF(is_subject_hotel, review_score, NULL)), 2) AS subject_review_score,
  ANY_VALUE(IF(is_subject_hotel, reviews, NULL)) AS subject_reviews,
  COUNTIF(NOT is_subject_hotel) AS compset_hotels,
  ROUND(AVG(IF(NOT is_subject_hotel, review_score, NULL)), 2) AS compset_avg_review_score,
  ROUND(MAX(IF(NOT is_subject_hotel, review_score, NULL)), 2) AS compset_best_review_score,
  MIN(IF(NOT is_subject_hotel, NULLIF(ranking, 0), NULL)) AS compset_best_ranking,
  {#- 1 = best review score among the subject and its comp set. -#}
  IF(
    ANY_VALUE(subject_score) IS NULL,
    NULL,
    1 + COUNTIF(NOT is_subject_hotel AND review_score > subject_score)
  ) AS subject_review_rank_in_compset,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM summaries
GROUP BY granularity, period, ota
