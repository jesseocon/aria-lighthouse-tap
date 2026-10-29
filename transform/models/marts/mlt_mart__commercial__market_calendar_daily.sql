{{
  config(
    alias=mlt_mart_table_name('commercial__market_calendar_daily'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

{#- One row per stay date: what the market looks like for that night.
    Demand and Smart Insights come from the latest daily snapshot that covers the
    date; events and holidays from every one that touches it. -#}

WITH demand AS (
  SELECT
    stay_date,
    as_of_date,
    demand_index,
    ROW_NUMBER() OVER (PARTITION BY stay_date ORDER BY as_of_date DESC) AS recency
  FROM {{ ref('stg_mlt_lighthouse_ota__demand') }}
),

demand_latest AS (
  SELECT
    latest.stay_date,
    latest.as_of_date AS demand_as_of_date,
    latest.demand_index,
    week_ago.demand_index AS demand_index_7d_ago
  FROM demand AS latest
  LEFT JOIN demand AS week_ago
    ON week_ago.stay_date = latest.stay_date
   AND week_ago.as_of_date = DATE_SUB(latest.as_of_date, INTERVAL 7 DAY)
  WHERE latest.recency = 1
),

insights AS (
  SELECT *
  FROM {{ ref('stg_mlt_lighthouse_ota__smart_insights') }}
  QUALIFY ROW_NUMBER() OVER (PARTITION BY stay_date ORDER BY as_of_date DESC, extracted_at DESC) = 1
),

event_days AS (
  SELECT
    CAST(day AS DATE) AS stay_date,
    STRUCT(
      e.event_id,
      e.name,
      e.category,
      e.importance,
      e.visitors,
      e.start_date,
      e.end_date,
      e.is_cancelled
    ) AS event
  FROM {{ ref('stg_mlt_lighthouse_ota__events') }} AS e,
    UNNEST(e.days) AS day
  WHERE NOT COALESCE(e.is_private, FALSE)
),

events_by_day AS (
  SELECT
    stay_date,
    COUNTIF(NOT COALESCE(event.is_cancelled, FALSE)) AS event_count,
    MAX(IF(COALESCE(event.is_cancelled, FALSE), NULL, event.importance)) AS max_event_importance,
    SUM(IF(COALESCE(event.is_cancelled, FALSE), 0, event.visitors)) AS event_visitors,
    ARRAY_AGG(event ORDER BY event.importance DESC, event.visitors DESC) AS events
  FROM event_days
  GROUP BY stay_date
),

holidays_by_day AS (
  SELECT
    CAST(day AS DATE) AS stay_date,
    STRING_AGG(DISTINCT h.name, '; ' ORDER BY h.name) AS holiday_names
  FROM {{ ref('stg_mlt_lighthouse_ota__holidays') }} AS h,
    UNNEST(h.days) AS day
  GROUP BY stay_date
),

calendar AS (
  SELECT stay_date FROM demand_latest
  UNION DISTINCT SELECT stay_date FROM insights
  UNION DISTINCT SELECT stay_date FROM events_by_day
  UNION DISTINCT SELECT stay_date FROM holidays_by_day
)

SELECT
  '{{ var("property_id") }}' AS property_id,
  calendar.stay_date,
  FORMAT_DATE('%A', calendar.stay_date) AS day_of_week,
  d.demand_as_of_date,
  d.demand_index,
  d.demand_index_7d_ago,
  d.demand_index - d.demand_index_7d_ago AS demand_index_change_7d,
  COALESCE(e.event_count, 0) AS event_count,
  e.max_event_importance,
  e.event_visitors,
  e.events,
  h.holiday_names IS NOT NULL AS is_holiday,
  h.holiday_names,
  i.as_of_date AS insights_as_of_date,
  i.own_rate,
  i.own_rate_pickup_vs_7_days_ago,
  i.median_compset_rate,
  i.median_compset_rate_pickup_vs_7_days_ago,
  i.occupancy,
  i.occupancy_stly,
  i.occupancy_pickup_vs_7_days_ago,
  i.room_nights,
  i.room_nights_rooms_left_to_sell,
  i.adr,
  i.adr_stly,
  i.stay_date_priority,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM calendar
LEFT JOIN demand_latest AS d USING (stay_date)
LEFT JOIN insights AS i USING (stay_date)
LEFT JOIN events_by_day AS e USING (stay_date)
LEFT JOIN holidays_by_day AS h USING (stay_date)
