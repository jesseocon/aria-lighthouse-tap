{{
  config(
    alias=mlt_stream_table_name('rate_strategy_base_rates'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'rate_strategy_base_rates'),
  ['hotel_id', 'compset_id', 'snapshot_week', 'base_rate_id'],
  ['extracted_at', '_sdc_batched_at']
) }}
