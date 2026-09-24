{{
  config(
    alias=mlt_mart_table_name('mart_parity_metasearch_loss'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

SELECT *
FROM {{ ref('stg_mlt_lighthouse_ota__parity_metasearch_loss') }}
