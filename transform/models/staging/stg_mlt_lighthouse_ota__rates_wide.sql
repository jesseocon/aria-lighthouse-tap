{%- set competitors = mlt_rates_competitor_columns() -%}

{{
  config(
    enabled=false,
    alias=mlt_stream_table_name('rates_wide'),
    tags=['silver', 'lighthouse_ota'],
  )
}}

select
  property_id,
  hotel_id,
  run_id,
  refreshed_at,
  any_value(refresh_label) as refresh_label,
  any_value(run_timestamp) as run_timestamp,
  stay_date,
  any_value(date_label) as date_label,
  month,
  channel_key,
  any_value(channel) as channel,
  rate_type_key,
  any_value(rate_type) as rate_type,
  compset_id,
  los,
  max_persons,
  device,
  room,
  meal,
  any_value(my_otb) as my_otb,
  any_value(my_otb_hover) as my_otb_hover,
  any_value(market_demand) as market_demand,
  any_value(events_hover) as events_hover,
  parse_json({{ mlt_rates_competitor_names_sql(competitors) }}) as competitor_names
  {%- for competitor in competitors -%}
  , {{ mlt_rates_wide_metric(competitor.key, 'rate', '') }}
  , {{ mlt_rates_wide_metric(competitor.key, 'hover_rate', '_hover_rate') }}
  , {{ mlt_rates_wide_metric(competitor.key, 'hover_room_name', '_hover_room_name') }}
  , {{ mlt_rates_wide_metric(competitor.key, 'hover_updated', '_hover_updated') }}
  , {{ mlt_rates_wide_metric(competitor.key, 'redirect_url', '_redirect_url') }}
  {%- endfor %}
from {{ ref('stg_mlt_lighthouse_ota__rates') }}
group by
  property_id,
  hotel_id,
  run_id,
  refreshed_at,
  stay_date,
  month,
  channel_key,
  rate_type_key,
  compset_id,
  los,
  max_persons,
  device,
  room,
  meal
