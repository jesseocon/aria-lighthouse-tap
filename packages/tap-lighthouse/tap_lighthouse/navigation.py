"""Lighthouse Day-by-day navigation inside the Spider iframe."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page

DayByDayView = str


@dataclass(frozen=True)
class DayByDayUrlOptions:
    start_date: str | None = None
    end_date: str | None = None
    as_of_date: str | None = None
    pickup_from_date: str | None = None


def resolve_day_by_day_url(
    hotel_id: str,
    view: DayByDayView = "strategy",
    options: DayByDayUrlOptions | None = None,
) -> str:
    opts = options or DayByDayUrlOptions()
    base = f"https://app.mylighthouse.com/hotel/{hotel_id}/day-by-day/{view}"
    params: list[str] = []
    if opts.start_date:
        params.append(f"startDate={opts.start_date}")
    if opts.end_date:
        params.append(f"endDate={opts.end_date}")
    if not params:
        return base
    return f"{base}?{'&'.join(params)}"


def get_spider_frame(page: Page, *, timeout_ms: int = 30_000) -> Frame:
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        for frame in page.frames:
            if re.search(r"spider\.kriyarevgen\.com/dashboards/day-by-day", frame.url, re.I):
                return frame
        page.wait_for_timeout(500)
    msg = "Timed out waiting for Spider day-by-day iframe"
    raise TimeoutError(msg)


def apply_spider_query_params(
    frame: Frame,
    view: DayByDayView,
    options: DayByDayUrlOptions,
) -> None:
    if not options.as_of_date and not options.pickup_from_date:
        return

    current = frame.url
    if "spider.kriyarevgen.com" not in current.lower():
        return

    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    parsed = urlparse(current)
    query = dict(parse_qsl(parsed.query))
    if options.as_of_date and view != "market-segments":
        query["asof"] = options.as_of_date
    if options.pickup_from_date:
        query["pickupFrom"] = options.pickup_from_date

    next_url = urlunparse(parsed._replace(query=urlencode(query)))
    if next_url == current:
        return

    frame.goto(next_url, wait_until="domcontentloaded")
    wait_for_day_by_day_table(frame, view=view)


def wait_for_day_by_day_table(
    frame: Frame,
    *,
    view: DayByDayView = "strategy",
    timeout_ms: int = 90_000,
) -> None:
    deadline = time.time() + (timeout_ms / 1000)
    last_log = -1

    while time.time() < deadline:
        info = frame.evaluate(
            """() => {
                const table = document.querySelector('table.analytics.day-by-day');
                const asOf = document.querySelector('[data-testid="as-of-date"], .as-of-date');
                return {
                    hasTable: !!table,
                    rowCount: table?.querySelectorAll('tbody tr').length ?? 0,
                    hasAsOfDate: !!asOf,
                };
            }""",
        )
        if view == "strategy" and (info.get("hasAsOfDate") or (info.get("hasTable") and info.get("rowCount", 0) > 0)):
            return

        elapsed = int(time.time() - (deadline - timeout_ms / 1000))
        if elapsed >= 10 and elapsed % 10 == 0 and elapsed != last_log:
            print(f"Waiting for Spider table ({view})… {elapsed}s")
            last_log = elapsed

        frame.page.wait_for_timeout(2000)

    msg = f"Timed out waiting for Day by day table ({view}) inside Spider iframe"
    raise TimeoutError(msg)


def wait_for_table_ready(
    frame: Frame,
    *,
    timeout_ms: int = 45_000,
    poll_ms: int = 1_000,
) -> None:
    """Wait for Spider table rows and loading indicators (SPAs never reach networkidle)."""
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        ready = frame.evaluate(
            """() => {
                const table = document.querySelector('table.analytics.day-by-day');
                if (!table) return false;
                const loading = document.querySelector(
                    '.loading-indicator, .spinner, [class*="loading"]',
                );
                if (loading && loading instanceof HTMLElement && loading.offsetParent !== null) {
                    return false;
                }
                const rows = table.querySelectorAll('tbody tr');
                if (rows.length < 5) return false;
                const cells = rows[0]?.querySelectorAll('td') ?? [];
                return cells.length > 5;
            }""",
        )
        if ready:
            return
        frame.page.wait_for_timeout(poll_ms)

    msg = "Timed out waiting for Spider table data to finish loading"
    raise TimeoutError(msg)


def navigate_to_day_by_day(
    page: Page,
    hotel_id: str,
    view: DayByDayView = "strategy",
    options: DayByDayUrlOptions | None = None,
) -> Frame:
    opts = options or DayByDayUrlOptions()
    url = resolve_day_by_day_url(hotel_id, view, opts)
    page.goto(url, wait_until="domcontentloaded")
    frame = get_spider_frame(page)
    apply_spider_query_params(frame, view, opts)
    wait_for_day_by_day_table(frame, view=view)
    wait_for_table_ready(frame)
    return frame
