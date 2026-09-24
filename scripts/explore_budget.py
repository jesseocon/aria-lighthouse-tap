#!/usr/bin/env python3
"""Explore Lighthouse budget table across months."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/tap-lighthouse"))

from singer_playwright.browser import BrowserConfig, BrowserRuntime
from tap_lighthouse.budget_export import extract_budget_rows
from tap_lighthouse.budget_navigation import navigate_to_budget

HOTEL_ID = "202158"
ENTRY_ID = "19564"
VARIANCE = "absolute"


def add_months(month: str, delta: int) -> str:
    year, mon = map(int, month.split("-"))
    mon += delta
    while mon > 12:
        mon -= 12
        year += 1
    while mon < 1:
        mon += 12
        year -= 1
    return f"{year:04d}-{mon:02d}"


def main() -> None:
    today = date.today()
    current_month = f"{today.year:04d}-{today.month:02d}"
    months_to_probe = [
        add_months(current_month, -1),
        current_month,
        add_months(current_month, 2),
    ]

    runtime = BrowserRuntime(BrowserConfig(storage_state_path="storage_state.json", headless=True))
    runtime.start()
    try:
        page = runtime.page
        all_results: dict[str, object] = {}

        for month in months_to_probe:
            url = navigate_to_budget(page, HOTEL_ID, entry_id=ENTRY_ID, month=month, variance=VARIANCE)
            headers, rows = extract_budget_rows(page)
            all_results[month] = {
                "url": url,
                "columns": headers,
                "row_count": len(rows),
                "sample_row": rows[0] if rows else {},
                "last_date_label": rows[-1].get("date_label") if rows else None,
            }
            print(f"{month}: {len(rows)} rows (last={rows[-1].get('date_label') if rows else 'n/a'})")

        out_dir = Path("workshop-runs")
        out_dir.mkdir(exist_ok=True)
        json_path = out_dir / "budget-explore.json"
        json_path.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")
        print(f"Wrote {json_path}")
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
