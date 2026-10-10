"""Singer schemas for the API-based v2 streams."""

from __future__ import annotations

from typing import Any

from singer_sdk import typing as th

from tap_lighthouse.lighthouse_api import ITEM_FIELDS, PARITY_ITEM_FIELDS
from tap_lighthouse.spider_api import MERGED_FIELDS, column_name

_ITEM_TYPES: dict[str, Any] = {
    "value": th.NumberType,
    "shop_value": th.NumberType,
    "vat": th.NumberType,
    "city_tax": th.NumberType,
    "other_taxes": th.NumberType,
    "difference_with_baserate": th.NumberType,
    "mealtype_included": th.IntegerType,
    "membershiptype": th.IntegerType,
    "max_persons": th.IntegerType,
    "platform": th.IntegerType,
    "position_to_baserate": th.IntegerType,
    "issue_type": th.IntegerType,
    "best_flex": th.BooleanType,
    "cancellable": th.BooleanType,
    "cancellation": th.BooleanType,
    "vat_incl": th.BooleanType,
    "city_tax_incl": th.BooleanType,
    "other_taxes_incl": th.BooleanType,
    "is_out_of_sync": th.BooleanType,
    "is_wholesale_rate": th.BooleanType,
    "is_baserate": th.BooleanType,
    "extract_datetime": th.DateTimeType,
}


def _item_properties(fields: tuple[str, ...]) -> list[th.Property]:
    return [
        *(th.Property(name, _ITEM_TYPES.get(name, th.StringType)) for name in fields),
        th.Property("rate_id", th.StringType),
        th.Property("labels", th.StringType),
        th.Property("is_sold_out", th.BooleanType),
    ]


def _run_properties() -> list[th.Property]:
    return [
        th.Property("record_hash", th.StringType, required=True),
        th.Property("run_id", th.StringType, required=True),
        th.Property("run_timestamp", th.DateTimeType, required=True),
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("month", th.StringType),
        th.Property("stay_date", th.DateType, required=True),
        th.Property("leadtime", th.IntegerType),
        th.Property("los", th.IntegerType),
        th.Property("persons", th.IntegerType),
    ]


def build_strategy_snapshot_v2_schema() -> dict[str, Any]:
    merged = [th.Property(column_name(f), th.NumberType) for f in MERGED_FIELDS if f != "groups"]
    return th.PropertiesList(
        th.Property("as_of_date", th.DateType, required=True),
        th.Property("stay_date", th.DateType, required=True),
        th.Property("pickup_from", th.DateType),
        th.Property("hotel_id", th.StringType, required=True),
        th.Property("spider_hotel_id", th.StringType),
        th.Property("hotel_name", th.StringType),
        th.Property("currency", th.StringType),
        *merged,
        th.Property(
            "groups",
            th.ArrayType(
                th.ObjectType(
                    th.Property("name", th.StringType),
                    th.Property("rooms", th.NumberType),
                    th.Property("revenue", th.NumberType),
                )
            ),
        ),
        th.Property("rate_channel", th.StringType),
        th.Property("rate_bar", th.BooleanType),
        th.Property("rate_los", th.IntegerType),
        th.Property("rate_guests", th.IntegerType),
        th.Property("subject_rate", th.NumberType),
        th.Property("subject_rate_variance", th.NumberType),
        th.Property("comp_set_rate_average", th.NumberType),
        th.Property("comp_set_rate_average_variance", th.NumberType),
        th.Property(
            "competitor_rates",
            th.ArrayType(
                th.ObjectType(
                    th.Property("vendor_id", th.StringType),
                    th.Property("name", th.StringType),
                    th.Property("rate", th.NumberType),
                    th.Property("rate_variance", th.NumberType),
                )
            ),
        ),
        th.Property("notes", th.StringType),
        th.Property("extracted_at", th.DateTimeType),
    ).to_dict()


def build_rates_v2_schema() -> dict[str, Any]:
    return th.PropertiesList(
        *_run_properties(),
        th.Property("channel_key", th.StringType),
        th.Property("channel", th.StringType),
        th.Property("ota", th.StringType),
        th.Property("rate_type_key", th.StringType),
        th.Property("rate_type", th.StringType),
        th.Property("compset_id", th.IntegerType),
        th.Property("compset_name", th.StringType),
        th.Property("hotelinfo_id", th.IntegerType),
        th.Property("hotel_name", th.StringType),
        th.Property("hotel_brand_code", th.StringType),
        th.Property("hotel_group", th.StringType),
        th.Property("is_subject", th.BooleanType),
        th.Property("item_position", th.IntegerType),
        th.Property("has_rate", th.BooleanType),
        *_item_properties(ITEM_FIELDS),
        th.Property("redirect_url", th.StringType),
        th.Property("my_otb_extract_date", th.DateType),
        th.Property("my_otb_rooms_booked", th.NumberType),
        th.Property("my_otb_transient_rooms", th.NumberType),
        th.Property("my_otb_group_rooms", th.NumberType),
        th.Property("my_otb_out_of_order", th.NumberType),
        th.Property("my_otb_capacity", th.NumberType),
        th.Property("my_otb_compare_extract_date", th.DateType),
        th.Property("my_otb_compare_rooms_booked", th.NumberType),
        th.Property("my_otb_compare_transient_rooms", th.NumberType),
        th.Property("my_otb_compare_group_rooms", th.NumberType),
        th.Property("my_otb_compare_out_of_order", th.NumberType),
        th.Property("my_otb_compare_capacity", th.NumberType),
        th.Property("market_demand", th.NumberType),
        th.Property("market_demand_compare_extract_date", th.DateType),
        th.Property("market_demand_compare", th.NumberType),
        th.Property(
            "events",
            th.ArrayType(
                th.ObjectType(
                    th.Property("name", th.StringType),
                    th.Property("category", th.StringType),
                    th.Property("start_date", th.DateType),
                    th.Property("end_date", th.DateType),
                    th.Property("visitors", th.IntegerType),
                    th.Property("is_cancelled", th.BooleanType),
                )
            ),
        ),
    ).to_dict()


def build_parity_list_v2_schema() -> dict[str, Any]:
    return th.PropertiesList(
        *_run_properties(),
        th.Property("hotelinfo_id", th.IntegerType),
        th.Property("hotel_name", th.StringType),
        th.Property("ota", th.StringType),
        th.Property("item_position", th.IntegerType),
        *_item_properties(PARITY_ITEM_FIELDS),
        th.Property("parity_status", th.StringType),
        th.Property("num_shops_major", th.IntegerType),
        th.Property("num_shops_other", th.IntegerType),
    ).to_dict()
