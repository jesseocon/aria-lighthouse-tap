"""Tests for CSV export parsing and enrichment."""

from __future__ import annotations

from tap_lighthouse.export import (
    BROWSER_EXPORT_BUNDLE,
    csv_text_to_records,
    enrich_snapshot_records,
    load_browser_export_bundle,
)


def test_vendored_browser_export_bundle_exists() -> None:
    assert BROWSER_EXPORT_BUNDLE.is_file()
    source = load_browser_export_bundle()
    assert "__ariaLighthouseExport" in source


def test_csv_text_to_records_reads_lighthouse_export_shape() -> None:
    csv_text = """as_of_date_date,on_the_books_ooo_rms_available,_hotel_id,_as_of_date,rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_hilton_garden_inn_boston_burlington_rate
1/2/25 Thu,2/181,202158,01/02/2025,$119
"""
    records = csv_text_to_records(csv_text)

    assert len(records) == 1
    first = records[0]
    assert first["as_of_date_date"] == "1/2/25 Thu"
    assert first["on_the_books_ooo_rms_available"] == "2/181"
    assert first["_hotel_id"] == "202158"
    assert first["_as_of_date"] == "01/02/2025"
    assert "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_hilton_garden_inn_boston_burlington_rate" in first


def test_enrich_snapshot_records_adds_singer_keys() -> None:
    rows = [{"as_of_date_date": "1/2/25 Thu", "_hotel_id": "202158"}]
    enriched = enrich_snapshot_records(rows, as_of_date="2025-01-02")

    assert enriched[0]["as_of_date"] == "2025-01-02"
    assert enriched[0]["stay_date"] == "2025-01-02"
    assert enriched[0]["record_hash"]
    assert enriched[0]["as_of_date_date"] == "1/2/25 Thu"


def test_enrich_snapshot_records_upserts_on_as_of_and_stay() -> None:
    first = enrich_snapshot_records(
        [{"as_of_date_date": "1/2/25 Thu", "on_the_books": "180"}],
        as_of_date="2025-01-02",
    )
    second = enrich_snapshot_records(
        [{"as_of_date_date": "1/2/25 Thu", "on_the_books": "179"}],
        as_of_date="2025-01-02",
    )

    assert first[0]["record_hash"] == second[0]["record_hash"]
    assert first[0]["stay_date"] == second[0]["stay_date"] == "2025-01-02"


def test_enrich_snapshot_records_skips_unparseable_stay_nights() -> None:
    enriched = enrich_snapshot_records(
        [{"as_of_date_date": "not-a-date", "_hotel_id": "202158"}],
        as_of_date="2025-01-02",
    )
    assert enriched == []
