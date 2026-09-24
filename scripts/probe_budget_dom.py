#!/usr/bin/env python3
"""Probe budget page DOM structure."""

from __future__ import annotations

import json
from pathlib import Path

from singer_playwright.browser import BrowserConfig, BrowserRuntime

PROBE_JS = """
() => {
  const normalize = (v) => (v ?? "").replace(/\\s+/g, " ").trim();
  const root = document.querySelector(".ic-product-tour-48864127-budget-table");
  const table = document.querySelector(".prism-table table, table");
  const ember = document.querySelector(".ember-table");

  const describe = (el, name) => {
    if (!el) return { name, found: false };
    return {
      name,
      found: true,
      tag: el.tagName,
      className: el.className,
      childTags: [...new Set(Array.from(el.children).map(c => c.tagName))].slice(0, 20),
      theadRows: el.querySelectorAll("thead tr").length,
      tbodyRows: el.querySelectorAll("tbody tr").length,
      etRows: el.querySelectorAll(".et-tr").length,
      thCount: el.querySelectorAll("th").length,
      tdCount: el.querySelectorAll("td").length,
      firstTh: normalize(el.querySelector("th")?.textContent),
      firstTd: normalize(el.querySelector("td")?.textContent),
    };
  };

  const headerSample = Array.from(document.querySelectorAll("thead tr, .et-header-row, [class*='header']"))
    .slice(0, 5)
    .map((row, i) => ({
      index: i,
      className: row.className,
      cells: Array.from(row.querySelectorAll("th, td, [role='columnheader']")).map(c => normalize(c.textContent)).slice(0, 15),
    }));

  return {
    root: describe(root, "budget-root"),
    table: describe(table, "table"),
    ember: describe(ember, "ember-table"),
    headerSample,
    monthLabel: normalize(document.querySelector("[class*='month'], h1, h2")?.textContent),
    buttonsNearMonth: Array.from(document.querySelectorAll("button"))
      .filter(b => b.closest("[class*='date'], [class*='month'], [class*='calendar']") || b.className.includes("icon-only"))
      .slice(0, 8)
      .map(b => ({ text: normalize(b.textContent), className: b.className.slice(0, 80) })),
  };
}
"""

URL = "https://app.mylighthouse.com/hotel/202158/budget?entryId=19564&variance=absolute&startDate=2026-09-01&endDate=2026-09-30"


def main() -> None:
    runtime = BrowserRuntime(BrowserConfig(storage_state_path="storage_state.json", headless=True))
    runtime.start()
    try:
        page = runtime.page
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        result = page.evaluate(PROBE_JS)
        out = Path("workshop-runs/budget-dom-probe.json")
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
