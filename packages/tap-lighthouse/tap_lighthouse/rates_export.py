"""Export the Lighthouse rates compset table with cell hovers."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from tap_lighthouse.parity_export import normalize_field_name, parse_stay_date, parse_tooltip_text

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

RATES_TABLE_SELECTOR = "div.rates-table-container table"

NOISE_TOOLTIPS = frozenset(
    {
        "Any room",
        "Any meal",
        "Compare",
        "Desktop",
        "Best flex",
        "Lowest",
        "Lowest flex",
        "3rd Party",
    },
)

EXTRACT_TABLE_JS = """
() => {
  const normalize = (v) => (v ?? "").replace(/\\s+/g, " ").trim();
  const table = document.querySelector("div.rates-table-container table");
  if (!table) return { error: "table not found", headers: [], rows: [] };
  const headers = Array.from(table.querySelectorAll("thead th")).map((th, i) => {
    const text = normalize(th.innerText);
    return text || `column_${i}`;
  });
  const rows = Array.from(table.querySelectorAll("tbody tr")).map((tr) => {
    const cells = Array.from(tr.querySelectorAll("td")).map((td) => {
      const link = td.querySelector("a[href]");
      return {
        text: normalize(td.innerText),
        href: link ? link.getAttribute("href") : "",
      };
    });
    return { cells };
  });
  return { headers, rows };
}
"""


def wait_for_rates_table(page: Page, *, timeout_ms: int = 60_000) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        ready = page.evaluate(
            """() => {
                const table = document.querySelector("div.rates-table-container table");
                if (!table) return false;
                const loading = document.querySelector(".prism-table.loading, .loading-indicator");
                if (loading && loading instanceof HTMLElement && loading.offsetParent !== null) {
                    return false;
                }
                return table.querySelectorAll("tbody tr").length >= 5;
            }""",
        )
        if ready:
            return
        page.wait_for_timeout(500)
    msg = "Timed out waiting for the rates table"
    raise TimeoutError(msg)


def _is_noise_tooltip(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned or cleaned in NOISE_TOOLTIPS:
        return True
    return cleaned.startswith("Updated ")


def _read_tooltip(page: Page) -> str:
    loc = page.locator(".ember-tooltip[role='tooltip']")
    for i in range(loc.count()):
        tip = loc.nth(i)
        try:
            if not tip.is_visible():
                continue
            text = tip.inner_text(timeout=500).strip()
        except Exception:  # noqa: BLE001
            continue
        if _is_noise_tooltip(text):
            continue
        return text
    return ""


def _hover_cell(page: Page, cell: Any, *, hover_delay_ms: int) -> str:
    target = cell.locator(".ember-tooltip-target").first
    use = target if target.count() else cell
    page.mouse.move(0, 0)
    page.wait_for_timeout(100)
    use.hover(timeout=3000)
    page.wait_for_timeout(hover_delay_ms)
    return _read_tooltip(page)


def _header_key(header: str) -> str:
    return normalize_field_name(header)


def column_action(header: str, cell_text: str) -> str:
    """Classify one rates cell.

    A headerless cell is the stay date when it looks like ``Sat 03/10``.
    Other headerless cells (the row pencil, a blank trailing column) are dropped.
    """
    key = _header_key(header)
    if not key or key.startswith("column_"):
        if re.search(r"\d{1,2}/\d{1,2}", cell_text):
            return "date"
        return "drop"
    return "keep"


def _date_label(cells: list[dict[str, str]]) -> str:
    for cell in cells:
        if re.search(r"\d{1,2}/\d{1,2}", cell.get("text") or ""):
            return cell["text"]
    return ""


def parse_rate_hover(text: str) -> dict[str, Any]:
    parsed = parse_tooltip_text(text)
    if parsed.get("tooltip_type") != "rate_detail":
        return parsed
    if parsed.get("hover_updated"):
        return parsed
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) >= 3:
        parsed["hover_updated"] = lines[-1]
    return parsed


def extract_rates_rows_with_hovers(
    page: Page,
    *,
    hover_delay_ms: int = 300,
) -> list[dict[str, Any]]:
    raw = page.evaluate(EXTRACT_TABLE_JS)
    if not isinstance(raw, dict) or raw.get("error"):
        msg = f"Rates table extract failed: {raw}"
        raise RuntimeError(msg)
    headers = [str(header) for header in raw.get("headers") or []]
    table_rows = list(raw.get("rows") or [])
    body_rows = page.locator(f"{RATES_TABLE_SELECTOR} tbody tr")
    extracted: list[dict[str, Any]] = []

    for row_index, table_row in enumerate(table_rows):
        cells = list(table_row.get("cells") or [])
        date_label = _date_label(cells)
        if not date_label:
            continue
        row_locator = body_rows.nth(row_index)
        events_hover = ""
        my_otb = ""
        my_otb_hover = ""
        market_demand = ""
        competitors: list[dict[str, str]] = []

        for col_index, header in enumerate(headers):
            if col_index >= len(cells):
                break
            cell = cells[col_index]
            key = _header_key(header)
            text = str(cell.get("text") or "")
            action = column_action(header, text)
            if action == "drop":
                continue
            if action == "date":
                try:
                    events_hover = _hover_cell(
                        page,
                        row_locator.locator("td").nth(col_index),
                        hover_delay_ms=hover_delay_ms,
                    )
                except Exception:  # noqa: BLE001
                    events_hover = ""
                continue
            if key == "my_otb":
                my_otb = text
                try:
                    my_otb_hover = _hover_cell(
                        page,
                        row_locator.locator("td").nth(col_index),
                        hover_delay_ms=hover_delay_ms,
                    )
                except Exception:  # noqa: BLE001
                    my_otb_hover = ""
                continue
            if key == "market_demand":
                market_demand = text
                continue
            competitors.append(
                {
                    "label": header,
                    "key": key,
                    "rate": text,
                    "href": str(cell.get("href") or ""),
                    "hover": "",
                },
            )

        for competitor in competitors:
            col_index = headers.index(competitor["label"])
            try:
                competitor["hover"] = _hover_cell(
                    page,
                    row_locator.locator("td").nth(col_index),
                    hover_delay_ms=hover_delay_ms,
                )
            except Exception as exc:  # noqa: BLE001
                competitor["hover_error"] = str(exc)

        logger.info(
            "rates hover %s competitors=%s events=%s",
            date_label,
            len(competitors),
            bool(events_hover),
        )
        extracted.append(
            {
                "date_label": date_label,
                "my_otb": my_otb,
                "my_otb_hover": my_otb_hover,
                "market_demand": market_demand,
                "events_hover": events_hover,
                "competitors": competitors,
            },
        )
    return extracted


def table_column_key(label: str) -> str:
    """Header slug that keeps hyphens and slashes, matching the rates table extract."""
    return re.sub(r"\s+", "_", label.strip()).lower()


def competitor_names(table_rows: list[dict[str, Any]]) -> dict[str, str]:
    """Map each wide competitor column key back to the scraped header text.

    The column key lowercases the header and turns spaces into underscores, which
    drops punctuation distinctions. The header text is the name to display.
    """
    names: dict[str, str] = {}
    for row in table_rows:
        for competitor in row.get("competitors") or []:
            label = str(competitor.get("label") or "").strip()
            if not label:
                continue
            names.setdefault(table_column_key(label), label)
    return names


def build_rates_wide_rows(table_rows: list[dict[str, Any]], *, month: str) -> list[dict[str, Any]]:
    """One JSON object per stay date, with each competitor hotel as its own column."""
    rows: list[dict[str, Any]] = []
    for row in table_rows:
        date_label = str(row.get("date_label") or "")
        if not date_label:
            continue
        wide: dict[str, Any] = {
            "date": date_label,
            "stay_date": parse_stay_date(date_label, month),
            "my_otb": str(row.get("my_otb") or ""),
            "my_otb_hover": str(row.get("my_otb_hover") or ""),
            "market_demand": str(row.get("market_demand") or ""),
            "events_hover": str(row.get("events_hover") or ""),
        }
        for competitor in row.get("competitors") or []:
            key = table_column_key(str(competitor.get("label") or ""))
            hover = parse_rate_hover(str(competitor.get("hover") or ""))
            wide[key] = str(competitor.get("rate") or "")
            wide[f"{key}_hover_rate"] = str(hover.get("hover_rate") or "")
            wide[f"{key}_hover_room_name"] = str(hover.get("hover_room_name") or "")
            wide[f"{key}_hover_updated"] = str(hover.get("hover_updated") or "")
            wide[f"{key}_redirect_url"] = str(competitor.get("href") or "")
        rows.append(wide)
    return rows


def build_rates_records(
    table_rows: list[dict[str, Any]],
    *,
    month: str,
    channel: str,
    channel_key: str,
    rate_type: str,
    rate_type_key: str,
    compset_id: str = "1",
    los: str = "1",
    max_persons: str = "2",
    device: str = "Desktop",
    room: str = "Any room",
    meal: str = "Any meal",
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in table_rows:
        date_label = str(row.get("date_label") or "")
        if not date_label:
            continue
        stay_date = parse_stay_date(date_label, month)
        for competitor in row.get("competitors") or []:
            hover = parse_rate_hover(str(competitor.get("hover") or ""))
            records.append(
                {
                    "date_label": date_label,
                    "stay_date": stay_date,
                    "month": month,
                    "channel": channel,
                    "channel_key": channel_key,
                    "rate_type": rate_type,
                    "rate_type_key": rate_type_key,
                    "compset_id": compset_id,
                    "los": los,
                    "max_persons": max_persons,
                    "device": device,
                    "room": room,
                    "meal": meal,
                    "my_otb": str(row.get("my_otb") or ""),
                    "my_otb_hover": str(row.get("my_otb_hover") or ""),
                    "market_demand": str(row.get("market_demand") or ""),
                    "events_hover": str(row.get("events_hover") or ""),
                    "competitor": str(competitor.get("label") or ""),
                    "competitor_key": table_column_key(str(competitor.get("label") or "")),
                    "rate": str(competitor.get("rate") or ""),
                    "hover_rate": str(hover.get("hover_rate") or ""),
                    "hover_room_name": str(hover.get("hover_room_name") or ""),
                    "hover_updated": str(hover.get("hover_updated") or ""),
                    "hover_text": str(hover.get("hover_text") or ""),
                    "redirect_url": str(competitor.get("href") or ""),
                },
            )
    return records


def enrich_rates_records(
    records: list[dict[str, Any]],
    *,
    run_id: str,
    run_timestamp: str,
    refreshed_at: str,
    refresh_label: str,
    sync_params: dict[str, Any],
    hotel_id: str,
) -> list[dict[str, Any]]:
    sync_params_json = json.dumps(sync_params, sort_keys=True, default=str)
    sync_params_hash = hashlib.sha256(sync_params_json.encode()).hexdigest()[:32]
    enriched: list[dict[str, Any]] = []
    for record in records:
        payload = {
            "run_id": run_id,
            "refreshed_at": refreshed_at,
            "stay_date": record["stay_date"],
            "channel_key": record["channel_key"],
            "rate_type_key": record["rate_type_key"],
            "competitor_key": record["competitor_key"],
            "month": record["month"],
        }
        record_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode(),
        ).hexdigest()[:32]
        enriched.append(
            {
                **record,
                "record_hash": record_hash,
                "run_id": run_id,
                "run_timestamp": run_timestamp,
                "refreshed_at": refreshed_at,
                "refresh_label": refresh_label,
                "sync_params": sync_params_json,
                "sync_params_hash": sync_params_hash,
                "hotel_id": str(hotel_id),
            },
        )
    return enriched
