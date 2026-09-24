#!/usr/bin/env python3
"""Validate expanded budget extraction via tap module."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / "Library/Caches/ms-playwright"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/singer-playwright"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/tap-lighthouse"))

from singer_playwright.browser import BrowserConfig, BrowserRuntime
from tap_lighthouse.budget_export import extract_budget_rows, wait_for_budget_table

URL = (
    "https://app.mylighthouse.com/hotel/202158/budget"
    "?entryId=19564&variance=absolute&startDate=2026-09-01&endDate=2026-09-30"
)


def main() -> None:
    runtime = BrowserRuntime(BrowserConfig(storage_state_path="storage_state.json", headless=True))
    runtime.start()
    try:
        page = runtime.page
        page.goto(URL, wait_until="domcontentloaded")
        wait_for_budget_table(page)
        _, rows = extract_budget_rows(page)
        by_level: dict[str, int] = {}
        for row in rows:
            lvl = str(row.get("row_level", "?"))
            by_level[lvl] = by_level.get(lvl, 0) + 1
        sample = next((r for r in rows if r.get("segment") == "GOVERNMENT"), rows[0] if rows else {})
        result = {"row_count": len(rows), "by_level": by_level, "sample": sample}
        print(json.dumps(result, indent=2))
        Path("workshop-runs/budget-expand-probe.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
