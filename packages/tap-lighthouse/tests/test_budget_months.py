"""Budget month resolution tests."""

from __future__ import annotations

from tap_lighthouse.budget_months import resolve_budget_months


def test_resolve_budget_months_range() -> None:
    months = resolve_budget_months(
        start_month="2026-08",
        forward_months=2,
        as_of_month="2026-09",
    )
    assert months == ["2026-08", "2026-09", "2026-10", "2026-11"]


def test_resolve_budget_months_defaults_to_anchor_when_no_start() -> None:
    months = resolve_budget_months(
        forward_months=1,
        as_of_month="2026-09",
    )
    assert months == ["2026-09", "2026-10"]
