"""Incremental replication value resolution (lookback / next_only / bookmark_only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tap_lighthouse.dates import (
    add_days_iso,
    compare_iso_dates,
    iter_iso_dates,
    next_iso_date,
    today_iso,
)


IncrementalMode = Literal["next_only", "bookmark_only", "lookback"]
Timeframe = Literal["days", "months"]


@dataclass(frozen=True)
class IncrementalConfig:
    mode: IncrementalMode = "lookback"
    timeframe: Timeframe = "days"
    timeframe_quantity: int = 7


def subtract_days(iso: str, days: int) -> str:
    return add_days_iso(iso, -days)


def resolve_bookmarked_replication_values(
    *,
    incremental: IncrementalConfig,
    upper_bound: str,
    bookmark_value: str,
) -> list[str]:
    if incremental.mode == "next_only":
        start = next_iso_date(bookmark_value)
        return iter_iso_dates(start, upper_bound)

    if incremental.mode == "bookmark_only":
        return [bookmark_value]

    if incremental.mode == "lookback":
        if incremental.timeframe != "days":
            msg = "Only day lookback is supported in tap-lighthouse v1"
            raise NotImplementedError(msg)
        start = subtract_days(upper_bound, incremental.timeframe_quantity - 1)
        return iter_iso_dates(start, upper_bound)

    msg = f"Unknown incremental mode: {incremental.mode}"
    raise ValueError(msg)


def resolve_incremental_values(
    *,
    bookmark_value: str | None,
    replication_key_matches: bool,
    full_refresh: bool,
    default_start: str,
    upper_bound: str | None = None,
    explicit_values: list[str] | None = None,
) -> list[str]:
    """Resolve ordered as_of_date values to sync."""
    upper = upper_bound or today_iso()

    if full_refresh or not bookmark_value or not replication_key_matches:
        start = explicit_values[0] if explicit_values else default_start
    else:
        start = next_iso_date(bookmark_value)

    if explicit_values:
        filtered = [
            value
            for value in explicit_values
            if (full_refresh or compare_iso_dates(value, start) >= 0)
            and compare_iso_dates(value, upper) <= 0
        ]
        if filtered:
            return filtered

    if compare_iso_dates(start, upper) > 0:
        return []

    return iter_iso_dates(start, upper)


def resolve_snapshot_as_of_dates(
    *,
    state: dict,
    stream_name: str,
    full_refresh: bool,
    default_start: str,
    incremental: IncrementalConfig,
    upper_bound: str | None = None,
) -> list[str]:
    upper = upper_bound or today_iso()
    bookmarks = state.get("bookmarks", {})
    stream_state = bookmarks.get(stream_name, {})
    bookmark_value = stream_state.get("replication_key_value")
    replication_key = stream_state.get("replication_key")

    if (
        not full_refresh
        and bookmark_value
        and replication_key == "as_of_date"
    ):
        return resolve_bookmarked_replication_values(
            incremental=incremental,
            upper_bound=upper,
            bookmark_value=str(bookmark_value),
        )

    return resolve_incremental_values(
        bookmark_value=str(bookmark_value) if bookmark_value else None,
        replication_key_matches=replication_key == "as_of_date",
        full_refresh=full_refresh,
        default_start=default_start,
        upper_bound=upper,
    )
