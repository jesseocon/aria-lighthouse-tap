{{
  config(
    enabled=false,
    alias=mlt_stream_table_name('forecast'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

{{ mlt_stg_monthly_hierarchical(source('mlt_lighthouse_ota', 'forecast')) }}
