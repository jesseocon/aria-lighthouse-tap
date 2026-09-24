{{
  config(
    alias=mlt_mart_table_name('mart_forecast'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

SELECT *
FROM {{ ref('stg_mlt_lighthouse_ota__forecast') }}
