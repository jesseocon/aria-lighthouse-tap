"""Explicit rates export columns for BigQuery Storage Write API."""

from __future__ import annotations

from singer_sdk import typing as th

RATES_EXPORT_COLUMNS: tuple[str, ...] = (
    "date_label",
    "channel",
    "channel_key",
    "rate_type",
    "rate_type_key",
    "compset_id",
    "los",
    "max_persons",
    "device",
    "room",
    "meal",
    "my_otb",
    "my_otb_hover",
    "market_demand",
    "events_hover",
    "competitor",
    "competitor_key",
    "rate",
    "hover_rate",
    "hover_room_name",
    "hover_updated",
    "hover_text",
    "redirect_url",
)


def build_rates_schema() -> dict:
    properties = [
        th.Property("record_hash", th.StringType, required=True),
        th.Property("run_id", th.StringType, required=True),
        th.Property("run_timestamp", th.StringType, required=True),
        th.Property("refreshed_at", th.StringType, required=True),
        th.Property("refresh_label", th.StringType, nullable=True),
        th.Property("sync_params", th.StringType, required=True),
        th.Property("sync_params_hash", th.StringType, required=True),
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("month", th.StringType, required=True),
        th.Property("stay_date", th.StringType, required=True),
    ]
    properties.extend(
        th.Property(name, th.StringType, nullable=True) for name in RATES_EXPORT_COLUMNS
    )
    return th.ObjectType(*properties).to_dict()
