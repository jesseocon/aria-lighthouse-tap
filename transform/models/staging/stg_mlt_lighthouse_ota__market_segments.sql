{{
  config(
    alias=mlt_stream_table_name('market_segments'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'market_segments'),
  ['as_of_date', 'stay_date', 'market_segment'],
  ['extracted_at', '_sdc_batched_at']
) }}
