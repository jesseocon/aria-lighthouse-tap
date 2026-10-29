{{
  config(
    alias=mlt_stream_table_name('events'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'events'),
  ['hotel_id', 'event_id'],
  ['extracted_at', '_sdc_batched_at']
) }}
