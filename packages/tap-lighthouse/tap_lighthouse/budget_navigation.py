"""Navigation helpers for Lighthouse budget view."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from tap_lighthouse.budget_export import month_bounds, wait_for_budget_table

if TYPE_CHECKING:
    from playwright.sync_api import Page


def resolve_budget_url(
    hotel_id: str,
    *,
    entry_id: str,
    month: str,
    variance: str = "absolute",
    base_url: str = "https://app.mylighthouse.com",
) -> str:
    start_date, end_date = month_bounds(month)
    params = {
        "entryId": entry_id,
        "variance": variance,
        "startDate": start_date,
        "endDate": end_date,
    }
    query = urlencode(params)
    return f"{base_url.rstrip('/')}/hotel/{hotel_id}/budget?{query}"


def navigate_to_budget(
    page: Page,
    hotel_id: str,
    *,
    entry_id: str,
    month: str,
    variance: str = "absolute",
    base_url: str = "https://app.mylighthouse.com",
    timeout_ms: int = 60_000,
) -> str:
    url = resolve_budget_url(
        hotel_id,
        entry_id=entry_id,
        month=month,
        variance=variance,
        base_url=base_url,
    )
    page.goto(url, wait_until="domcontentloaded")
    wait_for_budget_table(page, timeout_ms=timeout_ms)
    return page.url
