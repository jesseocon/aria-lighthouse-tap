"""Tests for incremental replication resolution."""

from __future__ import annotations

from tap_lighthouse.dates import today_iso
from tap_lighthouse.incremental import (
    IncrementalConfig,
    resolve_bookmarked_replication_values,
    resolve_snapshot_as_of_dates,
)


def test_lookback_from_upper_bound() -> None:
    upper = "2026-01-10"
    values = resolve_bookmarked_replication_values(
        incremental=IncrementalConfig(mode="lookback", timeframe_quantity=3),
        upper_bound=upper,
        bookmark_value="2026-01-01",
    )
    assert values == ["2026-01-08", "2026-01-09", "2026-01-10"]


def test_first_sync_uses_start_date() -> None:
    values = resolve_snapshot_as_of_dates(
        state={"bookmarks": {}},
        stream_name="strategy-snapshot",
        full_refresh=True,
        default_start="2026-01-01",
        incremental=IncrementalConfig(mode="lookback", timeframe_quantity=7),
        upper_bound="2026-01-03",
    )
    assert values == ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_end_date_caps_upper_bound() -> None:
    values = resolve_snapshot_as_of_dates(
        state={"bookmarks": {}},
        stream_name="strategy-snapshot",
        full_refresh=True,
        default_start="2026-01-01",
        incremental=IncrementalConfig(mode="lookback", timeframe_quantity=7),
        upper_bound="2026-01-05",
    )
    assert values == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]


def test_bookmarked_lookback() -> None:
    state = {
        "bookmarks": {
            "strategy-snapshot": {
                "replication_key": "as_of_date",
                "replication_key_value": "2026-01-05",
            },
        },
    }
    values = resolve_snapshot_as_of_dates(
        state=state,
        stream_name="strategy-snapshot",
        full_refresh=False,
        default_start="2026-01-01",
        incremental=IncrementalConfig(mode="lookback", timeframe_quantity=2),
        upper_bound="2026-01-10",
    )
    assert values == ["2026-01-09", "2026-01-10"]
