{{
  config(
    alias=mlt_stream_table_name('rate_strategy_cancellation'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'rate_strategy_cancellation'),
  ['hotel_id', 'compset_id', 'snapshot_week', 'policy_id'],
  ['extracted_at', '_sdc_batched_at']
) }}
