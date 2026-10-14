"""Tests for property_info stream map helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from property_info import build_stream_maps  # noqa: E402
from registry import get_property  # noqa: E402


def test_build_stream_maps_names_api_streams() -> None:
    prop = get_property("hilton-garden-inn-boston-burlington")
    stream_maps = build_stream_maps(prop)
    assert set(stream_maps) == {
        "strategy-snapshot-v2",
        "market-segments",
        "rate-plans",
        "length-of-stay",
        "room-type",
        "parity-list-v2",
        "rates-v2",
    }
    assert stream_maps["strategy-snapshot-v2"]["__alias__"] == (
        "mlt_lighthouse_ota__snapshot_daily_v2_hotel_202158"
    )
    assert stream_maps["parity-list-v2"]["__alias__"] == (
        "mlt_lighthouse_ota__parity_list_v2_hotel_202158"
    )
    json.dumps(stream_maps)
