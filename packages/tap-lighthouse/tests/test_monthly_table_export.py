"""Unit tests for monthly table enrichment."""

from __future__ import annotations

from tap_lighthouse.monthly_table_export import (
    _hierarchy_keys,
    enrich_monthly_records,
    hash_sync_params,
)


def test_enrich_monthly_records_unique_hash_per_segment() -> None:
    params = {"stream": "budget", "month": "2026-09"}
    params_hash = hash_sync_params(params)
    rows = [
        {
            "date_label": "Tue 01/09/2026",
            "row_level": "0",
            "row_label": "Tue 01/09/2026",
            "category": None,
            "segment": None,
            "budget_rms_value": "154",
        },
        {
            "date_label": "Tue 01/09/2026",
            "row_level": "2",
            "row_label": "GOVERNMENT",
            "category": "Transient",
            "segment": "GOVERNMENT",
            "budget_rms_value": "12",
        },
    ]
    records = enrich_monthly_records(
        rows,
        run_id="run-1",
        run_timestamp="2026-09-17T12:00:00+00:00",
        sync_params=params,
        sync_params_hash=params_hash,
        hotel_id="202158",
        month="2026-09",
    )
    assert len(records) == 2
    assert records[0]["stay_date"] == "2026-09-01"
    assert records[1]["segment"] == "GOVERNMENT"
    assert records[0]["record_hash"] != records[1]["record_hash"]
    assert records[0]["row_key"] == "2026-09-01"
    assert records[0]["parent_row_key"] is None
    assert records[1]["row_key"] == "2026-09-01|Transient|GOVERNMENT"
    assert records[1]["parent_row_key"] == "2026-09-01|Transient"
    assert records[1]["parent_date_key"] == "2026-09-01"
    assert records[1]["parent_category_key"] == "2026-09-01|Transient"


def test_hierarchy_keys_for_category_row() -> None:
    keys = _hierarchy_keys(
        stay_date="2026-09-01",
        row_level="1",
        category="Transient",
        segment=None,
    )
    assert keys == {
        "row_key": "2026-09-01|Transient",
        "parent_row_key": "2026-09-01",
        "date_row_key": "2026-09-01",
        "category_row_key": "2026-09-01|Transient",
        "parent_date_key": "2026-09-01",
        "parent_category_key": None,
    }
