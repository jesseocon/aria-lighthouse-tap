#!/usr/bin/env python3
"""Probe budget table row/cell structure."""

from __future__ import annotations

import json
import time
from pathlib import Path

from singer_playwright.browser import BrowserConfig, BrowserRuntime

WAIT_JS = """
() => {
  const normalize = (v) => (v ?? "").replace(/\\s+/g, " ").trim();
  const loading = document.querySelector(".table-loading-state-bar");
  const table = document.querySelector(".ic-product-tour-48864127-budget-table table, .prism-table table");
  const bodyText = normalize(table?.textContent ?? "");
  const hasDates = /\\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\\s+\\d{2}\\/\\d{2}\\/\\d{4}\\b/.test(bodyText);
  const hasTotal = /\\bTotal\\b/.test(bodyText);
  return {
    loadingVisible: !!loading && loading.offsetParent !== null,
    hasDates,
    hasTotal,
    textLen: bodyText.length,
    preview: bodyText.slice(0, 200),
  };
}
"""

ROW_JS = """
() => {
  const normalize = (v) => (v ?? "").replace(/\\s+/g, " ").trim();
  const table = document.querySelector(".ic-product-tour-48864127-budget-table table, .prism-table table");

  const theadRows = Array.from(table.querySelectorAll("thead tr"));
  const groupCells = Array.from(theadRows[0]?.querySelectorAll("th") ?? []);
  const metricCells = Array.from(theadRows[1]?.querySelectorAll("th") ?? []);

  const slug = (v) => normalize(v).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  const columns = [];
  let metricIdx = 0;
  for (const groupCell of groupCells) {
    const group = slug(groupCell.textContent) || "date";
    const span = parseInt(groupCell.getAttribute("colspan") || "1", 10);
    if (!groupCell.textContent.trim() && span === 1) {
      columns.push({ key: "date_label", group: "date", metric: "label" });
      continue;
    }
    for (let i = 0; i < span; i++) {
      const metricCell = metricCells[metricIdx++];
      const metric = slug(metricCell?.textContent) || `col_${columns.length}`;
      columns.push({ key: group === "date" ? "date_label" : `${group}_${metric}`, group, metric });
    }
  }

  const bodyRows = Array.from(table.querySelectorAll("tbody tr")).filter(tr => {
    const tds = tr.querySelectorAll("td");
    return tds.length > 1 || normalize(tds[0]?.textContent).match(/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)/);
  });

  const parseCell = (td) => {
    const text = normalize(td.textContent);
    if (!text) return { value: null, variance: null, raw: text };
    const m = text.match(/^(.+?)\\s+([+-][\\d,.]+)$/);
    if (m) return { value: m[1], variance: m[2], raw: text };
    return { value: text, variance: null, raw: text };
  };

  const rows = [];
  for (const tr of bodyRows) {
    const cells = Array.from(tr.querySelectorAll("td"));
    const dateLabel = normalize(cells[0]?.textContent);
    if (!dateLabel || /^total$/i.test(dateLabel)) continue;
    const record = { date_label: dateLabel };
    cells.forEach((td, i) => {
      const col = columns[i] || { key: `column_${i}` };
      const parsed = parseCell(td);
      record[col.key] = parsed.raw;
      if (parsed.variance) record[`${col.key}_variance`] = parsed.variance;
      record[`${col.key}_value`] = parsed.value;
    });
    rows.push(record);
  }

  return { columns: columns.map(c => c.key), bodyRowCount: bodyRows.length, rows };
}
"""

URL = "https://app.mylighthouse.com/hotel/202158/budget?entryId=19564&variance=absolute&startDate=2026-09-01&endDate=2026-09-30"


def wait_for_budget_table(page, timeout_s: int = 60) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        last = page.evaluate(WAIT_JS)
        if last.get("hasDates") and not last.get("loadingVisible"):
            return last
        page.wait_for_timeout(1000)
    return last


def main() -> None:
    runtime = BrowserRuntime(BrowserConfig(storage_state_path="storage_state.json", headless=True))
    runtime.start()
    try:
        page = runtime.page
        page.goto(URL, wait_until="domcontentloaded")
        status = wait_for_budget_table(page)
        print("wait status:", json.dumps(status, indent=2))
        result = page.evaluate(ROW_JS)
        print(json.dumps({**result, "rows": result.get("rows", [])[:2]}, indent=2))
        print(f"total rows: {len(result.get('rows', []))}")
        labels = [r.get("date_label") for r in result.get("rows", [])]
        print("last labels:", labels[-3:])
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
