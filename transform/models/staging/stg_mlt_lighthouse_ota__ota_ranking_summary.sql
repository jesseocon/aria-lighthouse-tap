{{
  config(
    alias=mlt_stream_table_name('ota_ranking_summary'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'ota_ranking_summary'),
  ['hotel_id', 'compset_id', 'hotelinfo_id', 'ota', 'granularity', 'period'],
  ['extracted_at', '_sdc_batched_at']
) }}
