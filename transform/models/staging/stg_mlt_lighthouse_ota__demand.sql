{{
  config(
    alias=mlt_stream_table_name('demand'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'demand'),
  ['hotel_id', 'as_of_date', 'stay_date'],
  ['extracted_at', '_sdc_batched_at']
) }}
