"""Bronze table naming in dbt source and macros."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_uses_hotel_keyed_bronze_table() -> None:
    source_yml = (ROOT / "transform" / "models" / "sources" / "mlt_lighthouse_ota.yml").read_text(
        encoding="utf-8"
    )
    for suffix in (
        "snapshot_daily_v2_hotel_",
        "market_segments_hotel_",
        "rate_plans_hotel_",
        "length_of_stay_hotel_",
        "room_type_hotel_",
        "parity_list_v2_hotel_",
        "rates_v2_hotel_",
    ):
        assert suffix in source_yml
    assert "var('hotel_id')" in source_yml
    assert "property_id" not in source_yml


def test_macro_defines_hotel_keyed_bronze_table() -> None:
    macro_sql = (ROOT / "transform" / "macros" / "mlt_warehouse_naming.sql").read_text(
        encoding="utf-8"
    )
    assert "mlt_bronze_snapshot_daily_table" in macro_sql
    assert "snapshot_daily_hotel_" in macro_sql
