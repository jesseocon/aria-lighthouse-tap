"""Registry schema and loader tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from registry import (  # noqa: E402
    bronze_budget_table,
    bronze_forecast_table,
    bronze_parity_list_table,
    bronze_snapshot_daily_table,
    get_property,
    list_slugs,
    load_registry,
    property_id_for_tier,
)


def test_registry_loads_with_example_property() -> None:
    registry = load_registry()
    assert registry["source"] == "mlt_lighthouse_ota"
    assert len(registry["properties"]) >= 1


def test_list_slugs_includes_hgi_burlington() -> None:
    slugs = list_slugs()
    assert "hilton-garden-inn-boston-burlington" in slugs


def test_get_property_returns_tiers_and_dimensions() -> None:
    prop = get_property("hilton-garden-inn-boston-burlington")
    assert prop["hotel_id"] == "202158"
    assert prop["prod_property_id"] == "cmr9gjpz60001js046zkgomo9"
    assert prop["dev_property_id"] == "cmrmb56w4000dbqu95a06jr1t"
    assert "hilton_garden_inn_boston_burlington" in prop["rate_shop_dimensions"]
    assert prop["parity_channel_dimensions"][0]["key"] == "brand_com"


def test_property_id_for_tier() -> None:
    prop = get_property("hilton-garden-inn-boston-burlington")
    assert property_id_for_tier(prop, "prod") == "cmr9gjpz60001js046zkgomo9"
    assert property_id_for_tier(prop, "dev") == "cmrmb56w4000dbqu95a06jr1t"


def test_bronze_snapshot_daily_table_name() -> None:
    table = bronze_snapshot_daily_table("mlt_lighthouse_ota", "202158")
    assert table == "mlt_lighthouse_ota__snapshot_daily_hotel_202158"


def test_bronze_parity_list_table_name() -> None:
    table = bronze_parity_list_table("mlt_lighthouse_ota", "202158")
    assert table == "mlt_lighthouse_ota__parity_list_hotel_202158"


def test_bronze_budget_table_name() -> None:
    table = bronze_budget_table("mlt_lighthouse_ota", "202158")
    assert table == "mlt_lighthouse_ota__budget_hotel_202158"


def test_bronze_forecast_table_name() -> None:
    table = bronze_forecast_table("mlt_lighthouse_ota", "202158")
    assert table == "mlt_lighthouse_ota__forecast_hotel_202158"
