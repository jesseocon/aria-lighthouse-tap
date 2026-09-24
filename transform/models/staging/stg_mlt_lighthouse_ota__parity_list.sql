{{
  config(
    alias=mlt_stream_table_name('parity_list'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

WITH raw AS (
  SELECT *
  FROM {{ source('mlt_lighthouse_ota', 'parity_list') }}
)

SELECT
  raw.* EXCEPT (run_timestamp, stay_date),
  {{ mlt_parse_parity_run_timestamp('run_timestamp') }} AS run_timestamp,
  SAFE_CAST(NULLIF({{ mlt_as_string('stay_date') }}, '') AS DATE) AS stay_date,
  DATE_DIFF(
    SAFE_CAST(NULLIF({{ mlt_as_string('stay_date') }}, '') AS DATE),
    DATE({{ mlt_parse_parity_run_timestamp('run_timestamp') }}),
    DAY
  ) AS lead_time_days,
  '{{ var("property_id") }}' AS property_id,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM raw
WHERE NULLIF({{ mlt_as_string('record_hash') }}, '') IS NOT NULL
  AND NULLIF({{ mlt_as_string('stay_date') }}, '') IS NOT NULL
  AND {{ mlt_parse_parity_run_timestamp('run_timestamp') }} IS NOT NULL
