"""Tests for parity-list explicit schema."""

from __future__ import annotations

from tap_lighthouse.parity_list_schema import PARITY_LIST_EXPORT_COLUMNS, build_parity_list_schema


def test_parity_list_schema_includes_core_and_export_columns() -> None:
    schema = build_parity_list_schema()
    props = schema["properties"]
    for name in (
        "record_hash",
        "run_timestamp",
        "stay_date",
        "_parity_entity_labels",
        "brand_com_links",
        "booking_com_hover_text",
        "expedia_hover_text",
        "priceline_hover_text",
        "loss_channels_on_metasearch_hover_channels",
        "lowest_rate_hover_rate",
        "lowest_rate_hover_room_name",
        "lowest_rate_hover_updated",
    ):
        assert name in props
    assert "column_7" not in PARITY_LIST_EXPORT_COLUMNS
    assert props["_row_index"]["type"] == ["integer", "null"]
