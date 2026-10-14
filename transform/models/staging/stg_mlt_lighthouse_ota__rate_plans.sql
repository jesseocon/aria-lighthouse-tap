{{
  config(
    alias=mlt_stream_table_name('rate_plans'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'rate_plans'),
  ['as_of_date', 'stay_date', 'market_segment', 'rate_plan'],
  ['extracted_at', '_sdc_batched_at']
) }}
