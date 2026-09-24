"""ISO date helpers for snapshot windows and incremental sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_snapshot_stay_date(raw: str) -> str:
    """Parse Lighthouse stay labels like ``1/2/25 Thu`` or ``9/15/26 Tue`` to ISO."""
    token = str(raw or "").strip()
    if not token:
        return ""
    date_part = token.rsplit(" ", 1)[0] if " " in token else token
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_part, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def format_iso_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def add_days_iso(iso: str, days: int) -> str:
    return format_iso_date(parse_iso_date(iso) + timedelta(days=days))


def compare_iso_dates(left: str, right: str) -> int:
    left_date = parse_iso_date(left)
    right_date = parse_iso_date(right)
    if left_date < right_date:
        return -1
    if left_date > right_date:
        return 1
    return 0


def next_iso_date(iso: str) -> str:
    return add_days_iso(iso, 1)


def iter_iso_dates(from_iso: str, to_iso: str) -> list[str]:
    if compare_iso_dates(from_iso, to_iso) > 0:
        msg = f"from ({from_iso}) must be on or before to ({to_iso})"
        raise ValueError(msg)
    values: list[str] = []
    current = from_iso
    while compare_iso_dates(current, to_iso) <= 0:
        values.append(current)
        current = next_iso_date(current)
    return values


def today_iso() -> str:
    return format_iso_date(date.today())


@dataclass(frozen=True)
class SnapshotWindow:
    as_of_date: str
    start_date: str
    end_date: str
    pickup_from_date: str


def build_snapshot_window(as_of_date: str, window_days: int = 365) -> SnapshotWindow:
    if window_days < 1:
        msg = f"window_days must be at least 1 (got {window_days})"
        raise ValueError(msg)
    parse_iso_date(as_of_date)
    end_date = add_days_iso(as_of_date, window_days - 1)
    return SnapshotWindow(
        as_of_date=as_of_date,
        start_date=as_of_date,
        end_date=end_date,
        pickup_from_date=as_of_date,
    )
