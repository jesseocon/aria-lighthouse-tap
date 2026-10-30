{{
  config(
    alias=mlt_mart_table_name('commercial__ota_reputation_monthly'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

{#- Subject vs comp set per OTA and month (period = YYYY/M). See macros/mlt_ota_reputation.sql. -#}

{{ mlt_ota_reputation('monthly') }}
