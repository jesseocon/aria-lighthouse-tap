"""Navigation helpers for Lighthouse forecast view."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from tap_lighthouse.entry_id import parse_entry_id_from_url, resolve_entry_id_from_redirect
from tap_lighthouse.monthly_table_export import month_bounds, wait_for_monthly_table
from tap_lighthouse.forecast_export import FORECAST_TABLE_SELECTOR

if TYPE_CHECKING:
    from playwright.sync_api import Page


def forecast_base_path(hotel_id: str, *, base_url: str = "https://app.mylighthouse.com") -> str:
    return f"{base_url.rstrip('/')}/hotel/{hotel_id}/forecast"


def resolve_forecast_entry_id(
    page: Page,
    hotel_id: str,
    *,
    base_url: str = "https://app.mylighthouse.com",
    configured_entry_id: str | None = None,
    timeout_ms: int = 30_000,
) -> tuple[str, str]:
    """Return (entry_id, source) where source is config or redirect."""
    if configured_entry_id:
        return str(configured_entry_id), "config"
    path = forecast_base_path(hotel_id, base_url=base_url)
    entry_id = resolve_entry_id_from_redirect(page, path=path, timeout_ms=timeout_ms)
    return entry_id, "redirect"


def resolve_forecast_url(
    hotel_id: str,
    *,
    entry_id: str,
    month: str | None = None,
    base_url: str = "https://app.mylighthouse.com",
) -> str:
    params: dict[str, str] = {"entryId": entry_id}
    if month:
        start_date, end_date = month_bounds(month)
        params["startDate"] = start_date
        params["endDate"] = end_date
    query = urlencode(params)
    return f"{forecast_base_path(hotel_id, base_url=base_url)}?{query}"


def navigate_to_forecast(
    page: Page,
    hotel_id: str,
    *,
    entry_id: str,
    month: str | None = None,
    base_url: str = "https://app.mylighthouse.com",
    timeout_ms: int = 60_000,
) -> str:
    url = resolve_forecast_url(
        hotel_id,
        entry_id=entry_id,
        month=month,
        base_url=base_url,
    )
    page.goto(url, wait_until="domcontentloaded")
    wait_for_monthly_table(page, selector=FORECAST_TABLE_SELECTOR, timeout_ms=timeout_ms)
    return page.url


def entry_id_from_current_url(page: Page) -> str | None:
    return parse_entry_id_from_url(page.url)
