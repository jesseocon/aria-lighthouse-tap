"""Singer schema for budget stream exports."""

from __future__ import annotations

from singer_sdk import typing as th

# Core metric groups observed on the budget table (columns vary by table layout).
BUDGET_METRIC_GROUPS: tuple[str, ...] = (
    "budget",
    "otb",
    "group_block",
    "ly_finals",
    "user_forecast",
    "bi_forecast",
    "finance_forecast",
    "rms_forecast",
)

BUDGET_METRICS: tuple[str, ...] = ("rms", "adr", "rev")


def _group_metric_columns() -> tuple[str, ...]:
    names: list[str] = []
    for group in BUDGET_METRIC_GROUPS:
        for metric in BUDGET_METRICS:
            prefix = f"{group}_{metric}"
            names.extend((prefix, f"{prefix}_value", f"{prefix}_variance"))
    return tuple(names)


def build_budget_schema() -> dict:
    properties = [
        th.Property("record_hash", th.StringType, required=True),
        th.Property("run_id", th.StringType, required=True),
        th.Property("run_timestamp", th.StringType, required=True),
        th.Property("sync_params", th.StringType, required=True),
        th.Property("sync_params_hash", th.StringType, required=True),
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("month", th.StringType, required=True),
        th.Property("stay_date", th.StringType, required=True),
        th.Property("date_label", th.StringType, nullable=True),
        th.Property("date_label_value", th.StringType, nullable=True),
        th.Property("date_label_variance", th.StringType, nullable=True),
        th.Property("row_level", th.StringType, nullable=True),
        th.Property("row_label", th.StringType, nullable=True),
        th.Property("category", th.StringType, nullable=True),
        th.Property("segment", th.StringType, nullable=True),
        th.Property("row_key", th.StringType, nullable=True),
        th.Property("parent_row_key", th.StringType, nullable=True),
        th.Property("date_row_key", th.StringType, nullable=True),
        th.Property("category_row_key", th.StringType, nullable=True),
        th.Property("parent_date_key", th.StringType, nullable=True),
        th.Property("parent_category_key", th.StringType, nullable=True),
    ]
    for name in _group_metric_columns():
        properties.append(th.Property(name, th.StringType, nullable=True))
    return th.ObjectType(
        *properties,
        additional_properties=th.StringType(nullable=True),
    ).to_dict()
