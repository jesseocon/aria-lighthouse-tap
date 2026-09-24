"""Shared monthly table extraction for Budget, Forecast, and similar views."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

DEFAULT_MONTHLY_TABLE_SELECTOR = ".prism-table table"

EXPAND_LEVEL_JS = """
(level) => {
  let clicked = 0;
  for (const tr of document.querySelectorAll(".ember-table .et-tr.table-row")) {
    if (!tr.className.includes(`table-row--level-${level}`)) continue;
    if (/^total$/i.test((tr.querySelector("p")?.textContent || "").trim())) continue;
    const btn = tr.querySelector("button.prism-button--icon-only");
    if (btn) {
      btn.click();
      clicked++;
    }
  }
  return clicked;
}
"""

MONTHLY_TABLE_JS = """
(selector) => {
  const normalize = (v) => (v ?? "").replace(/\\s+/g, " ").trim();
  const slug = (v) => normalize(v).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  const isDate = (t) => /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\\s+\\d{2}\\/\\d{2}\\/\\d{4}$/.test(t);

  const table = document.querySelector(selector);
  if (!table) return { error: "monthly table not found", rows: [] };

  const theadRows = Array.from(table.querySelectorAll("thead tr"));
  const groupCells = Array.from(theadRows[0]?.querySelectorAll("th") ?? []);
  const metricCells = Array.from(theadRows[1]?.querySelectorAll("th") ?? []);

  const expandedGroups = [];
  for (const groupCell of groupCells) {
    const group = slug(groupCell.textContent) || "date";
    const span = parseInt(groupCell.getAttribute("colspan") || "1", 10);
    for (let i = 0; i < span; i++) expandedGroups.push(group);
  }

  const columns = [];
  for (let i = 0; i < metricCells.length; i++) {
    const metric = slug(metricCells[i].textContent) || "value";
    const group = expandedGroups[i] || `group_${i}`;
    columns.push(group === "date" ? "date_label" : `${group}_${metric}`);
  }

  const rowLabel = (tr) => {
    const p = tr.querySelector("p.truncate, p");
    const fromP = normalize(p?.textContent || "");
    if (fromP) return fromP;
    const firstTd = tr.querySelector("td");
    const fromTd = normalize(firstTd?.innerText || "");
    if (fromTd) return fromTd.split("\\n").map((part) => part.trim()).filter(Boolean)[0] || fromTd;
    return normalize(tr.innerText || "").split("\\n").map((part) => part.trim()).filter(Boolean)[0] || "";
  };

  const parseCell = (text) => {
    const normalized = normalize(text);
    if (!normalized || normalized === "--") return { value: null, variance: null, raw: normalized };
    const m = normalized.match(/^(.+?)\\s+([+-][\\d,.]+)$/);
    if (m) return { value: m[1], variance: m[2], raw: normalized };
    return { value: normalized, variance: null, raw: normalized };
  };

  let currentDate = null;
  let currentCategory = null;
  const rows = [];

  for (const tr of document.querySelectorAll(".ember-table .et-tr.table-row")) {
    const levelMatch = tr.className.match(/table-row--level-(\\d+)/);
    if (!levelMatch) continue;
    const level = parseInt(levelMatch[1], 10);
    const label = rowLabel(tr);
    if (!label || /^total$/i.test(label)) continue;

    if (level === 0 && isDate(label)) {
      currentDate = label;
      currentCategory = null;
    } else if (level === 1) {
      currentCategory = label;
    }

    const cells = Array.from(tr.children).filter((el) => el.tagName === "TD");
    const record = {
      row_level: String(level),
      row_label: label,
      date_label: currentDate,
      category: level === 1 ? label : level >= 2 ? currentCategory : null,
      segment: level >= 2 ? label : null,
    };

    cells.forEach((cell, i) => {
      const key = columns[i] || `column_${i}`;
      if (key === "date_label") return;
      const parsed = parseCell(cell.textContent);
      record[key] = parsed.raw;
      record[`${key}_value`] = parsed.value;
      if (parsed.variance) record[`${key}_variance`] = parsed.variance;
    });
    rows.push(record);
  }

  return { columns: columns, row_count: rows.length, rows };
}
"""

WAIT_FOR_MONTHLY_TABLE_JS = """
(selector) => {
  const normalize = (v) => (v ?? "").replace(/\\s+/g, " ").trim();
  const table = document.querySelector(selector);
  const bodyText = normalize(table?.textContent ?? "");
  const hasDates = /\\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\\s+\\d{2}\\/\\d{2}\\/\\d{4}\\b/.test(bodyText);
  const loading = table?.querySelector(".table-loading-state-bar");
  const loadingVisible = !!loading && loading.offsetParent !== null;
  return { ready: hasDates && !loadingVisible, hasDates, loadingVisible };
}
"""

_DATE_LABEL_RE = re.compile(
    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{2})/(\d{2})/(\d{4})$",
    re.I,
)


def month_bounds(month: str) -> tuple[str, str]:
    year, mon = map(int, month.split("-"))
    last_day = calendar.monthrange(year, mon)[1]
    return date(year, mon, 1).isoformat(), date(year, mon, last_day).isoformat()


def parse_stay_date(date_label: str) -> str | None:
    match = _DATE_LABEL_RE.match(date_label.strip())
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def wait_for_monthly_table(
    page: Page,
    *,
    selector: str = DEFAULT_MONTHLY_TABLE_SELECTOR,
    timeout_ms: int = 60_000,
) -> None:
    deadline = page.evaluate("() => Date.now()") + timeout_ms
    status: dict[str, Any] = {}
    while page.evaluate("() => Date.now()") < deadline:
        status = page.evaluate(WAIT_FOR_MONTHLY_TABLE_JS, selector)
        if status.get("ready"):
            return
        page.wait_for_timeout(1000)
    msg = f"Timed out waiting for monthly table: {status}"
    raise TimeoutError(msg)


def expand_monthly_table_rows(
    page: Page,
    *,
    expand_delay_ms: int = 1200,
    max_level: int = 1,
) -> dict[str, int]:
    """Expand ember-table rows level-by-level (dates, then categories/segments).

    Expanding level 0 twice toggles collapse, so each level is clicked at most once.
    """
    stats: dict[str, int] = {}
    for level in range(max_level + 1):
        clicked = int(page.evaluate(EXPAND_LEVEL_JS, level))
        stats[f"level_{level}_clicked"] = clicked
        if clicked:
            page.wait_for_timeout(expand_delay_ms)
    return stats


def extract_monthly_table_rows(
    page: Page,
    *,
    selector: str = DEFAULT_MONTHLY_TABLE_SELECTOR,
    expand: bool = True,
    expand_delay_ms: int = 1200,
    max_expand_level: int = 1,
) -> tuple[list[str], list[dict[str, Any]]]:
    wait_for_monthly_table(page, selector=selector)
    if expand:
        expand_monthly_table_rows(
            page,
            expand_delay_ms=expand_delay_ms,
            max_level=max_expand_level,
        )
    result = page.evaluate(MONTHLY_TABLE_JS, selector)
    if result.get("error"):
        msg = str(result["error"])
        raise RuntimeError(msg)
    return list(result.get("columns") or []), list(result.get("rows") or [])


def new_run_metadata() -> tuple[str, str]:
    run_id = str(uuid.uuid4())
    run_timestamp = datetime.now(UTC).isoformat()
    return run_id, run_timestamp


def build_sync_params(
    *,
    hotel_id: str,
    entry_id: str,
    month: str,
    url: str,
    stream: str,
    **extra: Any,
) -> dict[str, Any]:
    start_date, end_date = month_bounds(month)
    params: dict[str, Any] = {
        "hotel_id": hotel_id,
        "entry_id": entry_id,
        "month": month,
        "start_date": start_date,
        "end_date": end_date,
        "stream": stream,
        "url": url,
    }
    params.update(extra)
    return params


def hash_sync_params(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _record_identity(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("date_label") or ""),
            str(row.get("category") or ""),
            str(row.get("segment") or ""),
            str(row.get("row_level") or ""),
            str(row.get("row_label") or ""),
        ],
    )


def _hierarchy_keys(
    *,
    stay_date: str,
    row_level: str | None,
    category: str | None,
    segment: str | None,
) -> dict[str, str | None]:
    """Stable join keys for nesting date → category → segment rows in SQL/dbt."""
    date_key = stay_date
    category_key = f"{stay_date}|{category}" if category else None
    level = str(row_level or "")

    if level == "0":
        row_key = date_key
        parent_row_key = None
    elif level == "1":
        row_key = category_key
        parent_row_key = date_key
    elif level == "2":
        row_key = f"{stay_date}|{category}|{segment}" if category and segment else None
        parent_row_key = category_key
    else:
        row_key = None
        parent_row_key = None

    return {
        "row_key": row_key,
        "parent_row_key": parent_row_key,
        "date_row_key": date_key,
        "category_row_key": category_key,
        "parent_date_key": date_key if level in {"1", "2"} else None,
        "parent_category_key": category_key if level == "2" else None,
    }


def enrich_monthly_records(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    run_timestamp: str,
    sync_params: dict[str, Any],
    sync_params_hash: str,
    hotel_id: str,
    month: str,
) -> list[dict[str, Any]]:
    sync_params_json = json.dumps(sync_params, sort_keys=True)
    enriched: list[dict[str, Any]] = []
    for row in rows:
        date_label = str(row.get("date_label") or "")
        stay_date = parse_stay_date(date_label)
        if not stay_date:
            continue
        record = dict(row)
        identity = _record_identity(record)
        record.update(
            {
                "run_id": run_id,
                "run_timestamp": run_timestamp,
                "sync_params": sync_params_json,
                "sync_params_hash": sync_params_hash,
                "hotel_id": hotel_id,
                "month": month,
                "stay_date": stay_date,
                **_hierarchy_keys(
                    stay_date=stay_date,
                    row_level=str(record.get("row_level") or ""),
                    category=record.get("category"),
                    segment=record.get("segment"),
                ),
                "record_hash": hashlib.sha256(
                    f"{run_id}|{identity}|{sync_params_hash}".encode(),
                ).hexdigest(),
            },
        )
        enriched.append(record)
    return enriched
