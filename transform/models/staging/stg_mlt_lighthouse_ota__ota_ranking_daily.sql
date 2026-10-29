{{
  config(
    alias=mlt_stream_table_name('ota_ranking_daily'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_latest(
  source('mlt_lighthouse_ota', 'ota_ranking_daily'),
  ['hotel_id', 'compset_id', 'as_of_date', 'stay_date', 'ota', 'hotelinfo_id'],
  ['extracted_at', '_sdc_batched_at']
) }}
