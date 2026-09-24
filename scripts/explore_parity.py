#!/usr/bin/env python3
"""Explore Lighthouse parity list DOM + hover tooltips."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/singer-playwright"))

from singer_playwright.browser import BrowserConfig, BrowserRuntime

URL = "https://app.mylighthouse.com/hotel/202158/parity/list?los=1&maxPersons=2&month=2026-09"
STORAGE = "storage_state.json"

WAIT_FOR_TABLE_JS = """
() => {
  const table = document.querySelector('.prism-table table, .ember-table table, table');
  if (!table) return { ready: false, reason: 'no table' };
  const loading = document.querySelector('.prism-table.loading');
  if (loading) return { ready: false, reason: 'loading class present' };
  const rows = table.querySelectorAll('tbody tr, .et-tr');
  return { ready: rows.length >= 5, rowCount: rows.length, reason: rows.length >= 5 ? 'ok' : 'waiting for rows' };
}
"""

EXTRACT_TABLE_JS = """
() => {
  const normalize = (v) => (v ?? "").replace(/\\s+/g, " ").trim().replace(/[$\\u200f\\u200e]/g, '').trim();
  const table = document.querySelector('.prism-table table, .ember-table table, table');
  if (!table) return { error: 'table not found', rows: [] };

  const headers = Array.from(table.querySelectorAll('thead th')).map((th, i) => {
    const text = normalize(th.textContent);
    return text || `column_${i}`;
  });

  const bodyRows = Array.from(table.querySelectorAll('tbody tr'));
  const rows = bodyRows.map((tr) => {
    const cells = Array.from(tr.querySelectorAll('td'));
    const record = {};
    cells.forEach((td, i) => {
      const key = (headers[i] || `column_${i}`).replace(/\\s+/g, '_').toLowerCase();
      record[key] = normalize(td.textContent);
      const link = td.querySelector('a[href*="redirect"]');
      if (link) {
        record[`${key}_href`] = link.getAttribute('href');
        record[`${key}_link_text`] = normalize(link.textContent);
      }
      const lossLinks = Array.from(td.querySelectorAll('a')).map((a) => ({
        text: normalize(a.textContent),
        href: a.getAttribute('href'),
      }));
      if (lossLinks.length) record[`${key}_links`] = lossLinks;
    });
    return record;
  });

  return { headers, rowCount: rows.length, rows };
}
"""


def wait_for_table(page, timeout_ms: int = 60_000) -> None:
    import time

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        status = page.evaluate(WAIT_FOR_TABLE_JS)
        if status.get("ready"):
            return
        page.wait_for_timeout(1000)
    msg = f"Timed out waiting for parity table: {status}"
    raise TimeoutError(msg)


def probe_hovers(page, max_cells: int = 5) -> list[dict]:
    """Hover price cells and capture tooltip content via Playwright."""
    results: list[dict] = []
    cells = page.locator('tbody tr td a[href*="redirect"]').all()[:max_cells]

    for cell in cells:
        entry: dict = {"link_text": "", "href": "", "tooltips": []}
        try:
            entry["link_text"] = cell.inner_text(timeout=2000)
            entry["href"] = cell.get_attribute("href") or ""
            cell.hover(timeout=3000)
            page.wait_for_timeout(600)

            tooltip_selectors = [
                '[role="tooltip"]',
                '[class*="tooltip"]',
                '[class*="popover"]',
                '.tippy-box',
                '[data-tippy-root]',
                '[class*="Tippy"]',
                '.ember-popover',
                '[class*="hover-card"]',
            ]
            for selector in tooltip_selectors:
                loc = page.locator(selector)
                count = loc.count()
                for i in range(min(count, 3)):
                    tip = loc.nth(i)
                    if tip.is_visible():
                        entry["tooltips"].append(
                            {
                                "selector": selector,
                                "text": tip.inner_text(timeout=1000)[:500],
                            },
                        )
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)
        results.append(entry)

    return results


def main() -> None:
    runtime = BrowserRuntime(
        BrowserConfig(storage_state_path=STORAGE, headless=True),
    )
    runtime.start()
    try:
        page = runtime.page
        page.goto(URL, wait_until="domcontentloaded")
        wait_for_table(page)

        table_data = page.evaluate(EXTRACT_TABLE_JS)
        print("=== TABLE EXTRACT ===")
        print(f"Rows: {table_data.get('rowCount', 0)}")
        print(f"Headers: {table_data.get('headers')}")
        if table_data.get("rows"):
            print("Sample row:")
            print(json.dumps(table_data["rows"][0], indent=2))

        print("\n=== HOVER PROBE (Playwright) ===")
        hovers = probe_hovers(page, max_cells=6)
        print(json.dumps(hovers, indent=2))

        out = Path("workshop-runs/parity-explore.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "url": URL,
            "table": {
                "headers": table_data.get("headers"),
                "row_count": table_data.get("rowCount"),
                "sample_rows": (table_data.get("rows") or [])[:5],
            },
            "hovers": hovers,
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote {out}")

        # Write sample CSV for user review
        rows = table_data.get("rows") or []
        if rows:
            csv_path = Path("workshop-runs/parity-sample.csv")
            import csv

            keys = sorted({k for r in rows for k in r})
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            print(f"Wrote {csv_path} ({len(rows)} rows)")
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
