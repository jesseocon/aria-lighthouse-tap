{{
  config(
    alias=mlt_stream_table_name('parity_metasearch_loss'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

WITH parity_rows AS (
  SELECT *
  FROM {{ ref('stg_mlt_lighthouse_ota__parity_list') }}
),

exploded AS (
  SELECT
    parity_rows.record_hash,
    parity_rows.hotel_id,
    parity_rows.property_id,
    parity_rows.stay_date,
    parity_rows.run_id,
    parity_rows.run_timestamp,
    parity_rows.sync_params_hash,
    parity_rows.sync_params,
    parity_rows.loss_channels_on_metasearch_hover_channels,
    NULLIF(JSON_VALUE(channel_json, '$.channel'), '') AS channel,
    NULLIF(JSON_VALUE(channel_json, '$.loss'), '') AS loss,
    NULLIF(JSON_VALUE(channel_json, '$.rate'), '') AS rate,
    NULLIF(JSON_VALUE(channel_json, '$.source'), '') AS source
  FROM parity_rows
  CROSS JOIN UNNEST(
    IF(
      NULLIF(parity_rows.loss_channels_on_metasearch_hover_channels, '') IS NULL,
      [],
      JSON_QUERY_ARRAY(PARSE_JSON(parity_rows.loss_channels_on_metasearch_hover_channels))
    )
  ) AS channel_json
  WHERE channel_json IS NOT NULL
)

SELECT
  record_hash,
  hotel_id,
  property_id,
  stay_date,
  run_id,
  run_timestamp,
  sync_params_hash,
  sync_params,
  loss_channels_on_metasearch_hover_channels,
  channel,
  loss,
  rate,
  source,
  {{ dbt_utils.generate_surrogate_key(['record_hash', 'channel', 'source', 'rate']) }} AS metasearch_loss_id,
  CURRENT_TIMESTAMP() AS _loaded_at
FROM exploded
WHERE channel IS NOT NULL
