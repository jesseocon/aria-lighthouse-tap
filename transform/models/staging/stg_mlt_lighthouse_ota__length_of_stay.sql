{{
  config(
    alias=mlt_stream_table_name('length_of_stay'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'length_of_stay'),
  ['as_of_date', 'stay_date', 'length_of_stay'],
  ['extracted_at', '_sdc_batched_at']
) }}
