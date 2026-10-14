{{
  config(
    enabled=false,
    alias=mlt_mart_table_name('commercial__parity_loss_daily'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

SELECT *
FROM {{ ref('stg_mlt_lighthouse_ota__parity_metasearch_loss') }}
