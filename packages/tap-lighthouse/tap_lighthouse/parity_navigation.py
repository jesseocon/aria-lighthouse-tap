"""Navigation helpers for Lighthouse parity list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tap_lighthouse.parity_export import wait_for_parity_table

if TYPE_CHECKING:
    from playwright.sync_api import Page


def resolve_parity_list_url(
    hotel_id: str,
    *,
    los: int = 1,
    max_persons: int = 2,
    month: str,
    base_url: str = "https://app.mylighthouse.com",
) -> str:
    return (
        f"{base_url.rstrip('/')}/hotel/{hotel_id}/parity/list"
        f"?los={los}&maxPersons={max_persons}&month={month}"
    )


def navigate_to_parity_list(
    page: Page,
    hotel_id: str,
    *,
    los: int = 1,
    max_persons: int = 2,
    month: str,
    base_url: str = "https://app.mylighthouse.com",
    timeout_ms: int = 60_000,
) -> str:
    url = resolve_parity_list_url(
        hotel_id,
        los=los,
        max_persons=max_persons,
        month=month,
        base_url=base_url,
    )
    page.goto(url, wait_until="domcontentloaded")
    wait_for_parity_table(page, timeout_ms=timeout_ms)
    return url
