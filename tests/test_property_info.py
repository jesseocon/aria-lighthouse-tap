"""Tests for property_info stream map helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from property_info import build_stream_maps  # noqa: E402
from registry import get_property  # noqa: E402


def test_build_stream_maps_includes_strategy_parity_budget_and_forecast() -> None:
    prop = get_property("hilton-garden-inn-boston-burlington")
    stream_maps = build_stream_maps(prop)
    assert stream_maps["strategy-snapshot"]["__alias__"] == (
        "mlt_lighthouse_ota__snapshot_daily_hotel_202158"
    )
    assert stream_maps["parity-list"]["__alias__"] == (
        "mlt_lighthouse_ota__parity_list_hotel_202158"
    )
    assert stream_maps["budget"]["__alias__"] == (
        "mlt_lighthouse_ota__budget_hotel_202158"
    )
    assert stream_maps["forecast"]["__alias__"] == (
        "mlt_lighthouse_ota__forecast_hotel_202158"
    )
    json.dumps(stream_maps)
