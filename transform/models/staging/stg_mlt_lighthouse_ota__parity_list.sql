{{
  config(
    alias=mlt_stream_table_name('parity_list_v2'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'parity_list_v2'),
  ['record_hash'],
  ['run_timestamp', '_sdc_batched_at']
) }}
