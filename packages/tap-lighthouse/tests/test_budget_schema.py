"""Tests for budget explicit schema."""

from __future__ import annotations

import json
from pathlib import Path

from tap_lighthouse.budget_schema import build_budget_schema

WORKSHOP_EXPORT = (
    Path(__file__).resolve().parents[3] / "workshop-runs" / "budget-export.json"
)


def test_budget_schema_includes_core_and_metric_columns() -> None:
    props = build_budget_schema()["properties"]
    for name in (
        "record_hash",
        "run_timestamp",
        "stay_date",
        "month",
        "date_label",
        "date_label_value",
        "budget_rms",
        "budget_rms_value",
        "otb_adr_variance",
        "rms_forecast_rev_value",
    ):
        assert name in props


def test_budget_schema_covers_workshop_export_keys() -> None:
    if not WORKSHOP_EXPORT.exists():
        return
    rows = json.loads(WORKSHOP_EXPORT.read_text(encoding="utf-8"))
    props = build_budget_schema()["properties"]
    missing: set[str] = set()
    for row in rows:
        missing.update(key for key in row if key not in props)
    assert not missing, f"Schema missing workshop export keys: {sorted(missing)}"
