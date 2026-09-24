"""Month iteration helpers for parity-list sync."""

from __future__ import annotations

from datetime import date


def parse_month(value: str) -> tuple[int, int]:
    year_str, month_str = value.split("-", 1)
    return int(year_str), int(month_str)


def format_month(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def current_month() -> str:
    today = date.today()
    return format_month(today.year, today.month)


def iter_months(start_month: str, end_month: str) -> list[str]:
    start_year, start_mon = parse_month(start_month)
    end_year, end_mon = parse_month(end_month)
    values: list[str] = []
    year, month = start_year, start_mon
    while (year, month) <= (end_year, end_mon):
        values.append(format_month(year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return values


def subtract_months(month: str, count: int) -> str:
    year, mon = parse_month(month)
    mon -= count
    while mon < 1:
        mon += 12
        year -= 1
    return format_month(year, mon)


def add_months(month: str, count: int) -> str:
    year, mon = parse_month(month)
    mon += count
    while mon > 12:
        mon -= 12
        year += 1
    return format_month(year, mon)


def resolve_parity_months(
    *,
    as_of_month: str | None = None,
    forward_months: int = 2,
) -> list[str]:
    """Return the current month plus ``forward_months`` future months.

    Lighthouse parity is forward-looking only; historical months disappear
    from the UI. Every sync therefore covers current, next, and next+1 when
    ``forward_months`` is 2.
    """
    start = as_of_month or current_month()
    ahead = max(0, int(forward_months))
    return iter_months(start, add_months(start, ahead))
