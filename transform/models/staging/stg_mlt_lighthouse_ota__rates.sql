{{
  config(
    alias=mlt_stream_table_name('rates'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

SELECT
  raw.* EXCEPT (run_timestamp, stay_date, refreshed_at),
  SAFE_CAST(NULLIF({{ mlt_as_string('stay_date') }}, '') AS DATE) AS stay_date,
  {{ mlt_parse_parity_run_timestamp('run_timestamp') }} AS run_timestamp,
  {{ mlt_parse_parity_run_timestamp('refreshed_at') }} AS refreshed_at,
  '{{ var("property_id") }}' AS property_id,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM {{ source('mlt_lighthouse_ota', 'rates') }} AS raw
WHERE NULLIF({{ mlt_as_string('record_hash') }}, '') IS NOT NULL
  AND NULLIF({{ mlt_as_string('stay_date') }}, '') IS NOT NULL
