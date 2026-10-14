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
    assert names == {
        "strategy-snapshot-v2",
        "market-segments",
        "rate-plans",
        "length-of-stay",
        "room-type",
        "parity-list-v2",
        "rates-v2",
    }
    strategy_v2 = next(stream for stream in streams if stream.name == "strategy-snapshot-v2")
    assert strategy_v2.replication_key == "as_of_date"
    assert strategy_v2.primary_keys == ("as_of_date", "stay_date")
    segments = next(stream for stream in streams if stream.name == "market-segments")
    assert segments.replication_key == "as_of_date"
    assert segments.primary_keys == ("as_of_date", "stay_date", "market_segment")
    rate_plans = next(stream for stream in streams if stream.name == "rate-plans")
    assert rate_plans.replication_key == "as_of_date"
    assert rate_plans.primary_keys == ("as_of_date", "stay_date", "market_segment", "rate_plan")
    length_of_stay = next(stream for stream in streams if stream.name == "length-of-stay")
    assert length_of_stay.replication_key == "as_of_date"
    assert length_of_stay.primary_keys == ("as_of_date", "stay_date", "length_of_stay")
    room_type = next(stream for stream in streams if stream.name == "room-type")
    assert room_type.replication_key == "as_of_date"
    assert room_type.primary_keys == ("as_of_date", "stay_date", "room_type")
    parity = next(stream for stream in streams if stream.name == "parity-list-v2")
    assert parity.replication_key == "run_timestamp"
    rates = next(stream for stream in streams if stream.name == "rates-v2")
    assert rates.replication_key == "run_timestamp"
