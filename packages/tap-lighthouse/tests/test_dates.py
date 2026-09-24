"""Tests for date helpers."""

from __future__ import annotations

import pytest

from tap_lighthouse.dates import (
    add_days_iso,
    build_snapshot_window,
    iter_iso_dates,
    parse_snapshot_stay_date,
)


def test_build_snapshot_window() -> None:
    window = build_snapshot_window("2026-01-01", window_days=365)
    assert window.as_of_date == "2026-01-01"
    assert window.start_date == "2026-01-01"
    assert window.end_date == "2026-12-31"


def test_iter_iso_dates() -> None:
    assert iter_iso_dates("2026-01-01", "2026-01-03") == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]


def test_add_days_iso() -> None:
    assert add_days_iso("2026-01-01", 1) == "2026-01-02"


def test_build_snapshot_window_invalid() -> None:
    with pytest.raises(ValueError):
        build_snapshot_window("2026-01-01", window_days=0)


def test_parse_snapshot_stay_date() -> None:
    assert parse_snapshot_stay_date("1/2/25 Thu") == "2025-01-02"
    assert parse_snapshot_stay_date("9/15/26 Tue") == "2026-09-15"
    assert parse_snapshot_stay_date("2026-09-15") == "2026-09-15"
    assert parse_snapshot_stay_date("") == ""
    assert parse_snapshot_stay_date("not-a-date") == ""
