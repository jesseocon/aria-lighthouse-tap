{{
  config(
    alias=mlt_stream_table_name('smart_insights'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'smart_insights'),
  ['hotel_id', 'as_of_date', 'stay_date', 'rate_type', 'ota'],
  ['extracted_at', '_sdc_batched_at']
) }}
