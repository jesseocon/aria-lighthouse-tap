"""Unit tests for budget export helpers."""

from __future__ import annotations

from tap_lighthouse.budget_export import hash_sync_params, parse_stay_date


def test_parse_stay_date() -> None:
    assert parse_stay_date("Tue 01/09/2026") == "2026-09-01"
    assert parse_stay_date("Total") is None


def test_hash_sync_params_stable() -> None:
    params = {"entry_id": "19564", "hotel_id": "202158", "month": "2026-09"}
    assert hash_sync_params(params) == hash_sync_params(dict(params))
