"""Explicit parity-list export columns for BigQuery Storage Write API."""

from __future__ import annotations

from singer_sdk import typing as th

from tap_lighthouse.parity_entity_labels import PARITY_CHANNEL_KEYS

# Every hover-column suffix `parse_tooltip_text` / `_apply_parsed_hover` can emit.
# target-bigquery Storage Write builds a proto from this list and rejects extras.
PARITY_CHANNEL_FIELD_SUFFIXES: tuple[str, ...] = (
    "",
    "_has_tooltip",
    "_parity_status",
    "_links",
    "_redirect_ota",
    "_from_date",
    "_tooltip_type",
    "_hover_rate",
    "_hover_room_name",
    "_hover_text",
    "_hover_updated",
    "_hover_channels",
)


def _parity_channel_export_columns() -> tuple[str, ...]:
    names: list[str] = []
    for key in PARITY_CHANNEL_KEYS:
        names.extend(f"{key}{suffix}" for suffix in PARITY_CHANNEL_FIELD_SUFFIXES)
    return tuple(names)


PARITY_LIST_EXPORT_COLUMNS: tuple[str, ...] = (
    "_row_index",
    "date_has_tooltip",
    "date_label",
    *_parity_channel_export_columns(),
    "_parity_entity_labels",
)


def build_parity_list_schema() -> dict:
    properties = [
        th.Property("record_hash", th.StringType, required=True),
        th.Property("run_id", th.StringType, required=True),
        th.Property("run_timestamp", th.StringType, required=True),
        th.Property("sync_params", th.StringType, required=True),
        th.Property("sync_params_hash", th.StringType, required=True),
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("month", th.StringType, required=True),
        th.Property("stay_date", th.StringType, required=True),
    ]
    for name in PARITY_LIST_EXPORT_COLUMNS:
        if name == "_row_index":
            properties.append(th.Property("_row_index", th.IntegerType, nullable=True))
        else:
            properties.append(th.Property(name, th.StringType, nullable=True))
    return th.ObjectType(
        *properties,
        additional_properties=th.StringType(nullable=True),
    ).to_dict()
