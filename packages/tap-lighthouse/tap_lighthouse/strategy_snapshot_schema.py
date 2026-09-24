"""Explicit strategy-snapshot export columns for BigQuery Storage Write API.

target-bigquery builds a protobuf schema from the Singer SCHEMA message.
additionalProperties alone is not enough for denormalized storage writes, so
we declare the known wide-export columns explicitly and keep additionalProperties
for any new Lighthouse export fields.
"""

from __future__ import annotations

from singer_sdk import typing as th

STRATEGY_SNAPSHOT_EXPORT_COLUMNS: tuple[str, ...] = (
    "as_of_date_date",
    "on_the_books_ooo_rms_available",
    "on_the_books_left_to_sell",
    "on_the_books",
    "on_the_books_total_occ_percentage",
    "on_the_books_adr",
    "revenue_rev",
    "revenue_revpar",
    "group_otb_block",
    "bar_based_stats_otb",
    "bar_based_stats_8_week_rolling_avg",
    "pickup_from_rooms",
    "pickup_from_adr_change",
    "pricing_and_forecast_rms_forecast",
    "pricing_and_forecast_market_demand",
    "pricing_and_forecast_r28_avg",
    "pricing_and_forecast_hurdle",
    "pricing_and_forecast_optimal_bar",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_hilton_garden_inn_boston_burlington_rate",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_hilton_garden_inn_boston_burlington_change",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_avg_comp_set_rate",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_avg_comp_set_change",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_boston_marriott_burlington_rate",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_boston_marriott_burlington_change",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_hampton_inn_boston_bedford_burlington_rate",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_hampton_inn_boston_bedford_burlington_change",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_crowne_plaza_boston_woburn_by_ihg_rate",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_crowne_plaza_boston_woburn_by_ihg_change",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_courtyard_by_marriott_boston_billerica_bedford_rate",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_courtyard_by_marriott_boston_billerica_bedford_change",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_hyatt_house_boston_burlington_rate",
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_hyatt_house_boston_burlington_change",
    "notes",
    "_exported_at",
    "_pickup_from_date",
    "_market_segment_comparison",
    "_rate_plan_comparison",
    "_rate_plan_segment",
    "_length_of_stay_comparison",
    "_room_type_comparison",
    "_last_year_stly_type",
    "_last_year_forecast_type",
    "_group_rates_forecast_type",
    "_day_by_day_view",
    "_hierarchy",
    "_exchange_rate_type",
    "_currency",
    "_property_name",
    "_view",
    "_pivot_section",
    "_pivot_parent_group",
    "_pivot_parent_group_slug",
    "_strategy_type",
    "_pivot_entity_labels",
)


def build_strategy_snapshot_schema() -> dict:
    properties = [
        th.Property("record_hash", th.StringType, required=True),
        th.Property("as_of_date", th.DateType, required=True),
        th.Property("stay_date", th.DateType, required=True),
        th.Property("_hotel_id", th.StringType),
        th.Property("_as_of_date", th.StringType),
        th.Property("_date_range_start", th.StringType),
        th.Property("_date_range_end", th.StringType),
    ]
    properties.extend(
        th.Property(name, th.StringType, nullable=True)
        for name in STRATEGY_SNAPSHOT_EXPORT_COLUMNS
    )
    return th.ObjectType(
        *properties,
        additional_properties=th.StringType(nullable=True),
    ).to_dict()
