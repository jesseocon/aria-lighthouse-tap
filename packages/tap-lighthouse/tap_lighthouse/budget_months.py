"""Month iteration helpers for budget sync."""

from __future__ import annotations

from tap_lighthouse.parity_months import add_months, current_month, iter_months


def resolve_budget_months(
    *,
    start_month: str | None = None,
    forward_months: int = 2,
    as_of_month: str | None = None,
) -> list[str]:
    """Return months from ``start_month`` through current + ``forward_months``.

    Budget history can extend far into the past via ``start_month`` (e.g.
    ``2020-01``). The upper bound is always the anchor month (today by
    default) plus ``forward_months``.
    """
    anchor = as_of_month or current_month()
    end_month = add_months(anchor, max(0, int(forward_months)))
    start = start_month or anchor
    if start > end_month:
        return []
    return iter_months(start, end_month)
