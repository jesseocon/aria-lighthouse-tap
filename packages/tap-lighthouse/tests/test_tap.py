"""Tap catalog smoke tests."""

from __future__ import annotations

from tap_lighthouse.tap import TapLighthouse


def test_discover_streams() -> None:
    tap = TapLighthouse(
        config={
            "storage_state_path": "storage_state.json",
            "hotel_id": "202158",
            "start_date": "2025-01-01",
        },
    )
    streams = tap.discover_streams()
    names = {stream.name for stream in streams}
    assert names == {"strategy-snapshot", "parity-list", "budget", "forecast"}
    parity = next(stream for stream in streams if stream.name == "parity-list")
    assert parity.replication_key == "run_timestamp"
    budget = next(stream for stream in streams if stream.name == "budget")
    assert budget.replication_key == "run_timestamp"
    assert budget.primary_keys == ("record_hash",)
    forecast = next(stream for stream in streams if stream.name == "forecast")
    assert forecast.replication_key == "run_timestamp"
