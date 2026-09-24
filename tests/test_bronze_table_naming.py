"""Bronze table naming in dbt source and macros."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_uses_hotel_keyed_bronze_table() -> None:
    source_yml = (ROOT / "transform" / "models" / "sources" / "mlt_lighthouse_ota.yml").read_text(
        encoding="utf-8"
    )
    assert "snapshot_daily_hotel_" in source_yml
    assert "var('hotel_id')" in source_yml
    assert "property_id" not in source_yml


def test_macro_defines_hotel_keyed_bronze_table() -> None:
    macro_sql = (ROOT / "transform" / "macros" / "mlt_warehouse_naming.sql").read_text(
        encoding="utf-8"
    )
    assert "mlt_bronze_snapshot_daily_table" in macro_sql
    assert "snapshot_daily_hotel_" in macro_sql
