"""Export Day-by-day tables using the vendored Lighthouse browser-export bundle."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tap_lighthouse.dates import parse_snapshot_stay_date

if TYPE_CHECKING:
    from playwright.sync_api import Frame

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
BROWSER_EXPORT_BUNDLE = _VENDOR_DIR / "browser-export.js"


def load_browser_export_bundle() -> str:
    if not BROWSER_EXPORT_BUNDLE.is_file():
        msg = f"Vendored browser export bundle missing: {BROWSER_EXPORT_BUNDLE}"
        raise FileNotFoundError(msg)
    return BROWSER_EXPORT_BUNDLE.read_text(encoding="utf-8")


def ensure_browser_exporter(frame: Frame, bundle_source: str) -> None:
    installed = frame.evaluate(
        "() => typeof globalThis.__ariaLighthouseExport === 'function'",
    )
    if installed:
        return
    frame.evaluate(bundle_source)


def export_in_browser_frame(
    frame: Frame,
    *,
    hotel_id: str,
    bundle_source: str,
) -> dict[str, Any]:
    """Run the in-page Day-by-day exporter inside the Spider iframe."""
    ensure_browser_exporter(frame, bundle_source)
    result = frame.evaluate(
        """
        async (options) => {
            const exporter = globalThis.__ariaLighthouseExport;
            if (!exporter) {
                throw new Error("Browser export bundle is not loaded in the Spider frame.");
            }
            return await exporter(options);
        }
        """,
        {
            "hotelId": hotel_id,
            "splitRateShopValues": True,
            "includeSummaryRows": False,
            "collectAllRows": True,
        },
    )
    return dict(result)


def csv_text_to_records(csv_text: str) -> list[dict[str, str]]:
    """Parse exporter CSV output into row dicts keyed by column label."""
    if not csv_text.strip():
        return []
    reader = csv.DictReader(io.StringIO(csv_text))
    return [{key: (value or "") for key, value in row.items()} for row in reader]


def extract_table_records(
    frame: Frame,
    *,
    hotel_id: str,
) -> list[dict[str, Any]]:
    bundle_source = load_browser_export_bundle()
    export_result = export_in_browser_frame(
        frame,
        hotel_id=hotel_id,
        bundle_source=bundle_source,
    )
    return csv_text_to_records(str(export_result.get("csv") or ""))


def enrich_snapshot_records(
    rows: list[dict[str, Any]],
    *,
    as_of_date: str,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        stay_date = parse_snapshot_stay_date(
            str(row.get("as_of_date_date") or row.get("date") or ""),
        )
        if not stay_date:
            continue
        record["as_of_date"] = as_of_date
        record["stay_date"] = stay_date
        record["record_hash"] = _record_hash(as_of_date, stay_date)
        enriched.append(record)
    return enriched


def _record_hash(as_of_date: str, stay_date: str) -> str:
    payload = json.dumps(
        {"as_of_date": as_of_date, "stay_date": stay_date},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
