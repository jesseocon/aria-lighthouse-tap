{{
  config(
    alias=mlt_stream_table_name('holidays'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'holidays'),
  ['hotel_id', 'holiday_id'],
  ['extracted_at', '_sdc_batched_at']
) }}
