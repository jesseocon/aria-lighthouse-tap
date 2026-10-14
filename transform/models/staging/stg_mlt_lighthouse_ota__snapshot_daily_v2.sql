{{
  config(
    alias=mlt_stream_table_name('snapshot_daily_v2'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'snapshot_daily_v2'),
  ['as_of_date', 'stay_date'],
  ['extracted_at', '_sdc_batched_at']
) }}
