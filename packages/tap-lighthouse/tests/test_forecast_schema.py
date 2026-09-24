"""Tests for forecast explicit schema."""

from __future__ import annotations

import json
from pathlib import Path

from tap_lighthouse.forecast_schema import build_forecast_schema

WORKSHOP_EXPORT = (
    Path(__file__).resolve().parents[3] / "workshop-runs" / "forecast-export.json"
)


def test_forecast_schema_includes_date_label_suffixes() -> None:
    props = build_forecast_schema()["properties"]
    for name in ("date_label", "date_label_value", "date_label_variance"):
        assert name in props


def test_forecast_schema_covers_workshop_export_keys() -> None:
    if not WORKSHOP_EXPORT.exists():
        return
    rows = json.loads(WORKSHOP_EXPORT.read_text(encoding="utf-8"))
    props = build_forecast_schema()["properties"]
    missing: set[str] = set()
    for row in rows:
        missing.update(key for key in row if key not in props)
    assert not missing, f"Schema missing workshop export keys: {sorted(missing)}"
