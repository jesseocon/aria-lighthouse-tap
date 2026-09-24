#!/usr/bin/env python3
"""Export forecast table to JSON + CSV for inspection."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/tap-lighthouse"))

from singer_playwright.browser import BrowserConfig, BrowserRuntime
from tap_lighthouse.forecast_export import (
    build_sync_params,
    enrich_forecast_records,
    extract_forecast_rows,
    hash_sync_params,
    new_run_metadata,
)
from tap_lighthouse.forecast_navigation import navigate_to_forecast, resolve_forecast_entry_id

HOTEL_ID = "202158"
MONTH = "2026-09"


def main() -> None:
    runtime = BrowserRuntime(
        BrowserConfig(storage_state_path="storage_state.json", headless=True),
    )
    runtime.start()
    try:
        page = runtime.page
        run_id, run_timestamp = new_run_metadata()
        entry_id, entry_id_source = resolve_forecast_entry_id(page, HOTEL_ID)
        print(f"Resolved entry_id={entry_id} (source={entry_id_source})")

        url = navigate_to_forecast(page, HOTEL_ID, entry_id=entry_id, month=MONTH)
        sync_params = build_sync_params(
            hotel_id=HOTEL_ID,
            entry_id=entry_id,
            month=MONTH,
            url=url,
            entry_id_source=entry_id_source,
        )
        sync_params_hash = hash_sync_params(sync_params)
        _, rows = extract_forecast_rows(page)
        records = enrich_forecast_records(
            rows,
            run_id=run_id,
            run_timestamp=run_timestamp,
            sync_params=sync_params,
            sync_params_hash=sync_params_hash,
            hotel_id=HOTEL_ID,
            month=MONTH,
        )

        out_dir = Path("workshop-runs")
        out_dir.mkdir(exist_ok=True)
        json_path = out_dir / "forecast-export.json"
        json_path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
        print(f"Wrote {json_path} ({len(records)} rows)")

        if records:
            csv_path = out_dir / "forecast-export.csv"
            keys = sorted({k for r in records for k in r})
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(records)
            print(f"Wrote {csv_path}")

            sample = records[0]
            print("\n=== Sample row (selected fields) ===")
            for k in sorted(sample):
                if k.endswith("_value") or k in {"stay_date", "date_label", "sync_params"}:
                    if sample[k]:
                        print(f"  {k}: {sample[k]}")
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
