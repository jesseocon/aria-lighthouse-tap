"""Singer schemas for the market-context streams (events, demand, rankings, rate strategy)."""

from __future__ import annotations

from typing import Any

from singer_sdk import typing as th

from tap_lighthouse.market_api import SMART_INSIGHT_KPIS

_DATES = th.ArrayType(th.StringType)


def _hotel_properties() -> list[th.Property]:
    return [
        th.Property("hotelinfo_id", th.IntegerType, required=True),
        th.Property("hotel_name", th.StringType),
        th.Property("is_subject_hotel", th.BooleanType),
    ]


def build_events_schema() -> dict[str, Any]:
    return th.PropertiesList(
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("event_id", th.StringType, required=True),
        th.Property("event_hotel", th.IntegerType),
        th.Property("name", th.StringType),
        th.Property("category", th.StringType),
        th.Property("location", th.StringType),
        th.Property("description", th.StringType),
        th.Property("url", th.StringType),
        th.Property("start_date", th.DateType),
        th.Property("end_date", th.DateType),
        th.Property("days", _DATES),
        th.Property("periods", th.ArrayType(th.StringType)),
        th.Property("labels", th.ArrayType(th.StringType)),
        th.Property("visitors", th.IntegerType),
        th.Property("exhibitors", th.IntegerType),
        th.Property("importance", th.IntegerType),
        th.Property("influence_radius", th.NumberType),
        th.Property("lat", th.NumberType),
        th.Property("lon", th.NumberType),
        th.Property("are_exact_coordinates", th.BooleanType),
        th.Property("status", th.StringType),
        th.Property("is_cancelled", th.BooleanType),
        th.Property("is_private", th.BooleanType),
        th.Property("is_unconfirmed", th.BooleanType),
        th.Property("is_new_event", th.BooleanType),
        th.Property("created_timestamp", th.DateTimeType),
        th.Property("last_update_timestamp", th.DateTimeType),
        th.Property("max_distance", th.IntegerType),
        th.Property("extracted_at", th.DateTimeType),
    ).to_dict()


def build_holidays_schema() -> dict[str, Any]:
    return th.PropertiesList(
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("holiday_id", th.StringType, required=True),
        th.Property("name", th.StringType),
        th.Property("start_date", th.DateType),
        th.Property("end_date", th.DateType),
        th.Property("days", _DATES),
        th.Property("countries", th.ArrayType(th.StringType)),
        th.Property("subscriptions", th.ArrayType(th.IntegerType)),
        th.Property("created_timestamp", th.DateTimeType),
        th.Property("last_update_timestamp", th.DateTimeType),
        th.Property("extracted_at", th.DateTimeType),
    ).to_dict()


def build_demand_schema() -> dict[str, Any]:
    return th.PropertiesList(
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("as_of_date", th.DateType, required=True),
        th.Property("stay_date", th.DateType, required=True),
        th.Property("demand_index", th.NumberType),
        th.Property("message", th.StringType),
        th.Property("extracted_at", th.DateTimeType),
    ).to_dict()


def build_smart_insights_schema() -> dict[str, Any]:
    return th.PropertiesList(
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("as_of_date", th.DateType, required=True),
        th.Property("stay_date", th.DateType, required=True),
        th.Property("insight_id", th.StringType),
        th.Property("stay_date_relevance", th.NumberType),
        th.Property("stay_date_priority", th.StringType),
        th.Property("connected_dates", _DATES),
        th.Property("rate_type", th.StringType),
        th.Property("ota", th.StringType),
        *(th.Property(name, th.NumberType) for name in SMART_INSIGHT_KPIS),
        th.Property("kpi_message", th.StringType),
        th.Property("kpis_extra", th.StringType, description="JSON: kpis keys not listed as columns"),
        th.Property("insight_entries", th.StringType, description="JSON: non-empty insight entries"),
        th.Property("recommendation_entries", th.StringType, description="JSON: non-empty recommendations"),
        th.Property("extracted_at", th.DateTimeType),
    ).to_dict()


def build_ranking_summary_schema() -> dict[str, Any]:
    return th.PropertiesList(
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("compset_id", th.IntegerType, required=True),
        *_hotel_properties(),
        th.Property("ota", th.StringType, required=True),
        th.Property("granularity", th.StringType, required=True),
        th.Property("period", th.StringType, required=True),
        th.Property("period_start", th.DateType),
        th.Property("ranking", th.IntegerType),
        th.Property("available_hotels", th.IntegerType),
        th.Property("review_score", th.NumberType),
        th.Property("reviews", th.IntegerType),
        th.Property("message", th.StringType),
        th.Property("summary_id", th.StringType),
        th.Property("extracted_at", th.DateTimeType),
    ).to_dict()


def build_ranking_daily_schema() -> dict[str, Any]:
    return th.PropertiesList(
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("compset_id", th.IntegerType, required=True),
        th.Property("as_of_date", th.DateType, required=True),
        th.Property("stay_date", th.DateType, required=True),
        th.Property("leadtime", th.IntegerType),
        th.Property("los", th.IntegerType),
        th.Property("ota", th.StringType, required=True),
        *_hotel_properties(),
        th.Property("ranking", th.IntegerType),
        th.Property("available_hotels", th.IntegerType),
        th.Property("review_score", th.NumberType),
        th.Property("reviews", th.IntegerType),
        th.Property("price_value", th.NumberType),
        th.Property("currency", th.StringType),
        th.Property("message", th.StringType),
        th.Property("shopped_at", th.DateTimeType),
        th.Property("cell_id", th.StringType),
        th.Property("extracted_at", th.DateTimeType),
    ).to_dict()


def _rate_strategy_common() -> list[th.Property]:
    return [
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("compset_id", th.IntegerType, required=True),
        th.Property("snapshot_week", th.DateType, required=True),
        *_hotel_properties(),
    ]


def _labels() -> list[th.Property]:
    return [
        th.Property("rs_type", th.StringType),
        th.Property("rs_subtype", th.StringType),
        th.Property("rs_subtype_label", th.StringType),
    ]


def build_rate_strategy_schema(kind: str) -> dict[str, Any]:
    tail = [
        th.Property("base_rate_ref", th.StringType),
        th.Property("message", th.StringType),
        th.Property("extracted_at", th.DateTimeType),
    ]
    if kind == "base_rates":
        props = [
            th.Property("base_rate_id", th.StringType, required=True),
            th.Property("room_type", th.StringType),
            th.Property("room_name", th.StringType),
            th.Property("pos", th.StringType),
            th.Property("meal_type", th.IntegerType),
            th.Property("is_cancellable", th.BooleanType),
            th.Property("is_base", th.BooleanType),
            th.Property("is_bar", th.BooleanType),
            th.Property("rate", th.NumberType),
            th.Property("currency", th.StringType),
            th.Property("message", th.StringType),
            th.Property("extracted_at", th.DateTimeType),
        ]
    elif kind == "discounts":
        props = [
            th.Property("strategy_id", th.StringType, required=True),
            *_labels(),
            th.Property(
                "value", th.NumberType, description="Fraction of the base rate (-0.02 = -2%), or an amount when is_absolute"
            ),
            th.Property("is_absolute", th.BooleanType),
            th.Property("frequency_weekday", th.IntegerType),
            th.Property("frequency_weekend", th.IntegerType),
            th.Property("discounted_price", th.NumberType),
            *tail,
        ]
    elif kind == "patterns":
        props = [th.Property("pattern_id", th.StringType, required=True), *_labels(), th.Property("rate", th.NumberType), *tail]
    elif kind == "cancellation":
        props = [
            th.Property("policy_id", th.StringType, required=True),
            th.Property("rs_subtype", th.StringType),
            th.Property("days_before_arrival", th.IntegerType),
            th.Property("cutoff_time", th.StringType),
            th.Property("frequency_weekday", th.IntegerType),
            th.Property("frequency_weekend", th.IntegerType),
            *tail,
        ]
    else:
        msg = f"Unknown rate strategy kind: {kind}"
        raise ValueError(msg)
    return th.PropertiesList(*_rate_strategy_common(), *props).to_dict()
