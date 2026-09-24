"""Strategy snapshot schema includes wide export columns for BigQuery."""

from __future__ import annotations

from tap_lighthouse.strategy_snapshot_schema import (
    STRATEGY_SNAPSHOT_EXPORT_COLUMNS,
    build_strategy_snapshot_schema,
)


def test_strategy_snapshot_schema_includes_wide_export_columns() -> None:
    schema = build_strategy_snapshot_schema()
    properties = schema["properties"]
    assert "on_the_books_ooo_rms_available" in properties
    assert "stay_date" in properties
    assert "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_hilton_garden_inn_boston_burlington_rate" in properties
    assert len(properties) >= len(STRATEGY_SNAPSHOT_EXPORT_COLUMNS) + 4
