"""Tests for incremental as_of_date resolution."""

from __future__ import annotations

from tap_lighthouse.incremental import resolve_snapshot_as_of_dates


def test_first_sync_uses_start_date() -> None:
    values = resolve_snapshot_as_of_dates(
        bookmark=None,
        start_date="2026-01-01",
        lookback_days=7,
        upper_bound="2026-01-03",
    )
    assert values == ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_bookmark_today_still_looks_back() -> None:
    values = resolve_snapshot_as_of_dates(
        bookmark="2026-01-10",
        start_date="2026-01-01",
        lookback_days=7,
        upper_bound="2026-01-10",
    )
    assert values[0] == "2026-01-03"
    assert values[-1] == "2026-01-10"


def test_missed_days_start_from_bookmark_minus_lookback() -> None:
    values = resolve_snapshot_as_of_dates(
        bookmark="2026-01-01",
        start_date="2025-12-01",
        lookback_days=7,
        upper_bound="2026-01-10",
    )
    assert values[0] == "2025-12-25"
    assert values[-1] == "2026-01-10"
    assert len(values) == 17


def test_start_after_upper_bound_is_empty() -> None:
    values = resolve_snapshot_as_of_dates(
        bookmark=None,
        start_date="2026-02-01",
        lookback_days=7,
        upper_bound="2026-01-10",
    )
    assert values == []
