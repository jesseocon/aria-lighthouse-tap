"""Export Lighthouse parity list table with per-cell hover tooltips."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

from tap_lighthouse.parity_entity_labels import DROPPED_PARITY_FIELDS, build_parity_entity_labels

PARITY_TABLE_SELECTOR = ".prism-table table, .ember-table table"

FILTER_BAR_TOOLTIPS = frozenset(
    {
        "Member rate",
        "Any room",
        "Lowest",
        "Desktop",
        "1 night",
        "2 guests",
        "Any meal",
        "Default POS",
    },
)

HOVER_COLUMN_KEYS = frozenset(
    {
        "brand_com",
        "booking_com",
        "expedia",
        "priceline",
        "loss_channels_on_metasearch",
        "lowest_rate",
    },
)

WAIT_FOR_TABLE_JS = """
() => {
  const table = document.querySelector('.prism-table table, .ember-table table');
  if (!table) return { ready: false, reason: 'no table' };
  if (document.querySelector('.prism-table.loading')) return { ready: false, reason: 'loading' };
  const rows = table.querySelectorAll('tbody tr');
  return { ready: rows.length >= 5, rowCount: rows.length };
}
"""

EXTRACT_STATIC_JS = """
() => {
  const normalize = (v) => (v ?? "").replace(/\\s+/g, " ").trim().replace(/[$\\u200f\\u200e]/g, '').trim();
  const table = document.querySelector('.prism-table table, .ember-table table');
  if (!table) return { error: 'table not found', headers: [], rows: [] };

  const headers = Array.from(table.querySelectorAll('thead th')).map((th, i) => {
    const text = normalize(th.textContent);
    return (text || `column_${i}`).replace(/\\s+/g, '_').toLowerCase();
  });

  const parseHref = (href) => {
    if (!href) return {};
    try {
      const params = new URLSearchParams(href.split('?')[1] || '');
      return {
        ota: params.get('ota'),
        from_date: params.get('fromDate'),
        hotel_id: params.get('hotelId'),
        los: params.get('los'),
        persons: params.get('persons'),
      };
    } catch { return {}; }
  };

  const cellHasTooltip = (td) => {
    if (td.querySelector('.ember-tooltip-target')) return true;
    if (td.querySelector('[role="tooltip"]')) return true;
    if (td.querySelector('.ember-tooltip-base')) return true;
    return false;
  };

  const bodyRows = Array.from(table.querySelectorAll('tbody tr'));
  const rows = bodyRows.map((tr, rowIndex) => {
    const cells = Array.from(tr.querySelectorAll('td'));
    const record = { _row_index: rowIndex };
    cells.forEach((td, i) => {
      const rawKey = headers[i] || `column_${i}`;
      const key = rawKey;
      record[key] = normalize(td.textContent);
      record[`${key}_has_tooltip`] = cellHasTooltip(td);
      const parityClass = td.querySelector('[class*="parity-"]');
      if (parityClass) {
        const m = (parityClass.className || '').match(/parity-[a-z]+/);
        if (m) record[`${key}_parity_status`] = m[0];
      }
      const links = Array.from(td.querySelectorAll('a[href*="redirect"]')).map((a) => ({
        text: normalize(a.textContent),
        href: a.getAttribute('href'),
        ...parseHref(a.getAttribute('href')),
      }));
      if (links.length) {
        record[`${key}_links`] = links;
        const primary = links[0];
        if (primary.ota) record[`${key}_redirect_ota`] = primary.ota;
        if (primary.from_date) record[`${key}_from_date`] = primary.from_date;
      }
    });
    return record;
  });

  return { headers, rows };
}
"""


def normalize_field_name(header: str) -> str:
    """Convert table header slug to Singer-safe field name."""
    value = header.strip().lower().replace(".", "_").replace(" ", "_")
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "column"


def parse_stay_date(date_label: str, month: str) -> str:
    """Parse display label like Thu 17/09 into ISO stay_date using YYYY-MM month context."""
    match = re.search(r"(\d{1,2})/(\d{1,2})", date_label or "")
    if not match:
        msg = f"Cannot parse stay date from label: {date_label!r}"
        raise ValueError(msg)
    day = int(match.group(1))
    mon = int(match.group(2))
    year_str, month_str = month.split("-", 1)
    year = int(year_str)
    month_num = int(month_str)
    if mon != month_num:
        year = year + 1 if mon < month_num else year - 1
    return date(year, mon, day).isoformat()


def wait_for_parity_table(page: Page, *, timeout_ms: int = 60_000) -> None:
    deadline = time.time() + timeout_ms / 1000
    last_status: dict[str, Any] = {"ready": False}
    while time.time() < deadline:
        last_status = page.evaluate(WAIT_FOR_TABLE_JS)
        if last_status.get("ready"):
            return
        page.wait_for_timeout(1000)
    msg = f"Timed out waiting for parity table: {last_status}"
    raise TimeoutError(msg)


def parse_tooltip_text(text: str) -> dict[str, Any]:
    """Parse tab/newline separated tooltip content into structured fields."""
    text = re.sub(r"[\u200f\u200e]", "", text).strip()
    if not text:
        return {}

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return {"tooltip_type": "raw", "hover_text": text}

    header = lines[0].lower()
    if header.startswith("rate") and "room name" in header:
        if len(lines) >= 2:
            parts = re.split(r"\t+", lines[1])
            result: dict[str, Any] = {"tooltip_type": "rate_detail"}
            if len(parts) >= 1:
                result["hover_rate"] = parts[0].strip()
            if len(parts) >= 2:
                result["hover_room_name"] = parts[1].strip()
            if len(parts) >= 3:
                result["hover_updated"] = parts[2].strip()
            return result

    if header.startswith("channel"):
        channels = []
        for line in lines[1:]:
            parts = re.split(r"\t+", line)
            if len(parts) >= 2:
                channels.append(
                    {
                        "channel": parts[0].strip(),
                        "rate": parts[1].strip(),
                        "loss": parts[2].strip() if len(parts) > 2 else "",
                        "source": parts[3].strip() if len(parts) > 3 else "",
                    },
                )
        return {"tooltip_type": "loss_channels", "hover_channels": channels}

    if len(lines) == 1:
        return {"tooltip_type": "simple", "hover_text": lines[0]}

    return {"tooltip_type": "raw", "hover_text": text}


def _is_noise_tooltip(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    if cleaned in FILTER_BAR_TOOLTIPS:
        return True
    if cleaned.startswith("Updated "):
        return True
    return False


def _dismiss_tooltips(page: Page) -> None:
    page.mouse.move(0, 0)
    page.wait_for_timeout(150)


def _read_scoped_tooltip(page: Page, *, previous_text: str = "") -> str:
    selectors = (
        "#ember-basic-dropdown-wormhole .ember-tooltip",
        "#ember-basic-dropdown-wormhole [role='tooltip']",
        ".ember-tooltip[role='tooltip']",
        ".ember-popover",
    )
    for selector in selectors:
        loc = page.locator(selector)
        for i in range(loc.count()):
            tip = loc.nth(i)
            try:
                if not tip.is_visible():
                    continue
                text = tip.inner_text(timeout=500).strip()
                if _is_noise_tooltip(text):
                    continue
                if previous_text and text == previous_text:
                    continue
                return text
            except Exception:  # noqa: BLE001
                continue
    return ""


def _wait_for_tooltip(page: Page, *, previous_text: str = "", timeout_ms: int = 1500) -> str:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        text = _read_scoped_tooltip(page, previous_text=previous_text)
        if text:
            return text
        page.wait_for_timeout(100)
    return ""


def _resolve_hover_target(td_locator: Any) -> Any | None:  # noqa: ANN401
    for selector in (
        ".ember-tooltip-target",
        "[role='tooltip']",
        ".ember-tooltip-base",
    ):
        target = td_locator.locator(selector)
        if target.count() > 0:
            return target.first
    return None


def _should_hover_cell(record: dict[str, Any], col_key: str) -> bool:
    field = normalize_field_name(col_key)
    if field not in HOVER_COLUMN_KEYS:
        return False
    if record.get(f"{field}_has_tooltip"):
        return True
    value = str(record.get(field) or "").strip()
    if not value or value in {"--", "No issues"}:
        return field == "loss_channels_on_metasearch"
    return True


def _apply_parsed_hover(record: dict[str, Any], col_key: str, parsed: dict[str, Any]) -> None:
    field = normalize_field_name(col_key)
    for key, value in parsed.items():
        if key == "hover_channels":
            record[f"{field}_hover_channels"] = json.dumps(value, sort_keys=True)
        else:
            record[f"{field}_{key}"] = value


def _normalize_row_keys(row: dict[str, Any], headers: list[str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {"_row_index": row.get("_row_index")}
    for header in headers:
        field = normalize_field_name(header)
        if field in DROPPED_PARITY_FIELDS:
            continue
        raw = row.get(header)
        if raw is None:
            continue
        normalized[field] = raw
        for suffix in ("_has_tooltip", "_parity_status", "_links", "_redirect_ota", "_from_date"):
            src = f"{header}{suffix}"
            if src in row:
                dest = f"{field}{suffix}"
                if dest in DROPPED_PARITY_FIELDS:
                    continue
                normalized[dest] = row[src]
    if "date" in normalized:
        normalized["date_label"] = normalized.pop("date")
    return _drop_parity_fields(normalized)


def _drop_parity_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in DROPPED_PARITY_FIELDS}


def _serialize_parity_value(value: Any) -> Any:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def _prepare_parity_record(record: dict[str, Any]) -> dict[str, Any]:
    prepared = _drop_parity_fields(record)
    serialized: dict[str, Any] = {}
    for key, value in prepared.items():
        if value is None:
            continue
        serialized[key] = _serialize_parity_value(value)
    serialized["_parity_entity_labels"] = json.dumps(
        build_parity_entity_labels(),
        sort_keys=True,
    )
    return serialized


def extract_parity_rows_with_hovers(
    page: Page,
    *,
    include_hovers: bool = True,
    hover_delay_ms: int = 300,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Extract parity table rows; optionally hover OTA cells for tooltip detail."""
    wait_for_parity_table(page)
    static = page.evaluate(EXTRACT_STATIC_JS)
    if static.get("error"):
        msg = static["error"]
        raise RuntimeError(msg)

    headers: list[str] = list(static.get("headers") or [])
    rows = [_normalize_row_keys(row, headers) for row in static.get("rows") or []]

    if not include_hovers:
        return headers, rows

    table = page.locator(PARITY_TABLE_SELECTOR)
    body_rows = table.locator("tbody tr")
    row_count = body_rows.count()
    last_tooltip = ""

    for row_idx in range(row_count):
        row_loc = body_rows.nth(row_idx)
        tds = row_loc.locator("td")
        record = rows[row_idx]

        for col_idx, col_key in enumerate(headers):
            if not _should_hover_cell(record, col_key):
                continue

            td = tds.nth(col_idx)
            target = _resolve_hover_target(td)
            if target is None:
                continue

            field = normalize_field_name(col_key)
            try:
                _dismiss_tooltips(page)
                target.hover(timeout=3000)
                tooltip_text = _wait_for_tooltip(page, previous_text=last_tooltip)
                if tooltip_text:
                    last_tooltip = tooltip_text
                    parsed = parse_tooltip_text(tooltip_text)
                    _apply_parsed_hover(record, col_key, parsed)
                _dismiss_tooltips(page)
                page.wait_for_timeout(hover_delay_ms)
            except Exception as exc:  # noqa: BLE001
                record[f"{field}_hover_error"] = str(exc)

    return headers, rows


def enrich_parity_records(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    run_timestamp: str,
    sync_params: dict[str, Any],
    sync_params_hash: str,
    hotel_id: str,
    month: str,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    sync_params_json = json.dumps(sync_params, sort_keys=True, default=str)

    for row in rows:
        record = dict(row)
        date_label = str(record.pop("date_label", record.get("date", "")))
        record["date_label"] = date_label
        record["stay_date"] = parse_stay_date(date_label, month)
        record["hotel_id"] = hotel_id
        record["month"] = month
        record["run_id"] = run_id
        record["run_timestamp"] = run_timestamp
        record["sync_params"] = sync_params_json
        record["sync_params_hash"] = sync_params_hash
        record["record_hash"] = _record_hash(
            run_id=run_id,
            stay_date=record["stay_date"],
            sync_params_hash=sync_params_hash,
        )
        enriched.append(_prepare_parity_record(record))
    return enriched


def _record_hash(*, run_id: str, stay_date: str, sync_params_hash: str) -> str:
    payload = json.dumps(
        {"run_id": run_id, "stay_date": stay_date, "sync_params_hash": sync_params_hash},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def new_run_metadata() -> tuple[str, str]:
    from uuid import uuid4

    run_id = str(uuid4())
    run_timestamp = datetime.now().astimezone().isoformat()
    return run_id, run_timestamp
