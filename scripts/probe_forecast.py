#!/usr/bin/env python3
"""Probe forecast page DOM, entryId redirect, and month navigation."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/singer-playwright"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/tap-lighthouse"))

from singer_playwright.browser import BrowserConfig, BrowserRuntime
from tap_lighthouse.budget_export import extract_budget_rows, month_bounds, wait_for_budget_table

BASE = "https://app.mylighthouse.com/hotel/202158/forecast"
TABLE_SEL = ".prism-table table, table"


def entry_id_from_url(url: str) -> str | None:
    params = parse_qs(urlparse(url).query)
    values = params.get("entryId") or params.get("entryid")
    return values[0] if values else None


def forecast_url(entry_id: str | None, month: str | None = None) -> str:
    if month:
        start, end = month_bounds(month)
        q = f"entryId={entry_id}&startDate={start}&endDate={end}" if entry_id else f"startDate={start}&endDate={end}"
    elif entry_id:
        q = f"entryId={entry_id}"
    else:
        return BASE
    return f"{BASE}?{q}"


def main() -> None:
    runtime = BrowserRuntime(BrowserConfig(storage_state_path="storage_state.json", headless=True))
    runtime.start()
    try:
        page = runtime.page
        results: dict[str, object] = {}

        # Resolve entryId via redirect
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        entry_id = entry_id_from_url(page.url)
        results["redirect"] = {"url": page.url, "entry_id": entry_id}

        # Current month extract
        wait_for_budget_table(page, timeout_ms=60_000)  # same wait pattern
        cols, rows = extract_budget_rows(page)  # same table shape
        results["current"] = {"columns": cols[:10], "row_count": len(rows), "sample": rows[0] if rows else {}}

        # August via startDate/endDate
        aug_url = forecast_url(entry_id, "2026-08")
        page.goto(aug_url, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        wait_for_budget_table(page)
        _, aug_rows = extract_budget_rows(page)
        results["2026-08"] = {"url": page.url, "row_count": len(aug_rows), "last": aug_rows[-1].get("date_label") if aug_rows else None}

        out = Path("workshop-runs/forecast-probe.json")
        out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(json.dumps(results, indent=2, default=str))
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
