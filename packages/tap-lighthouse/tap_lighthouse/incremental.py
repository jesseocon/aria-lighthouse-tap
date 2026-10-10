"""Incremental as_of_date resolution."""

from __future__ import annotations

from tap_lighthouse.dates import (
    add_days_iso,
    compare_iso_dates,
    iter_iso_dates,
    today_iso,
)


def resolve_snapshot_as_of_dates(
    *,
    bookmark: str | None,
    start_date: str,
    lookback_days: int,
    upper_bound: str | None = None,
) -> list[str]:
    """As-of dates to sync: start_date when there is no bookmark, else bookmark minus lookback_days."""
    upper = upper_bound or today_iso()
    start = add_days_iso(bookmark, -lookback_days) if bookmark else start_date
    if compare_iso_dates(start, upper) > 0:
        return []
    return iter_iso_dates(start, upper)
