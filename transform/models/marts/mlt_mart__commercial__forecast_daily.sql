{{
  config(
    enabled=false,
    alias=mlt_mart_table_name('commercial__forecast_daily'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

SELECT *
FROM {{ ref('stg_mlt_lighthouse_ota__forecast') }}
