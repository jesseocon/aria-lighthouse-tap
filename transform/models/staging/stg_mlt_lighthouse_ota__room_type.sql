{{
  config(
    alias=mlt_stream_table_name('room_type'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'room_type'),
  ['as_of_date', 'stay_date', 'room_type'],
  ['extracted_at', '_sdc_batched_at']
) }}
