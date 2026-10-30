{{
  config(
    alias=mlt_mart_table_name('commercial__ota_reputation_weekly'),
    tags=['gold', 'lighthouse_ota'],
  )
}}

{#- Subject vs comp set per OTA and ISO week (period = YYYY/WW). See macros/mlt_ota_reputation.sql. -#}

{{ mlt_ota_reputation('weekly') }}
