#!/usr/bin/env python3
"""Export parity list with hover tooltips to JSON + CSV."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/tap-lighthouse"))

from singer_playwright.browser import BrowserConfig, BrowserRuntime
from tap_lighthouse.parity_export import enrich_parity_records, extract_parity_rows_with_hovers, new_run_metadata
from tap_lighthouse.parity_navigation import navigate_to_parity_list
from tap_lighthouse.parity_provenance import build_sync_params, hash_sync_params

URL_MONTH = "2026-09"
HOTEL_ID = "202158"


def main() -> None:
    runtime = BrowserRuntime(
        BrowserConfig(storage_state_path="storage_state.json", headless=True),
    )
    runtime.start()
    try:
        page = runtime.page
        run_id, run_timestamp = new_run_metadata()
        url = navigate_to_parity_list(
            page,
            HOTEL_ID,
            los=1,
            max_persons=2,
            month=URL_MONTH,
        )
        sync_params = build_sync_params(
            hotel_id=HOTEL_ID,
            month=URL_MONTH,
            los=1,
            max_persons=2,
            url=url,
            page=page,
        )
        sync_params_hash = hash_sync_params(sync_params)
        _, rows = extract_parity_rows_with_hovers(page, include_hovers=True)
        records = enrich_parity_records(
            rows,
            run_id=run_id,
            run_timestamp=run_timestamp,
            sync_params=sync_params,
            sync_params_hash=sync_params_hash,
            hotel_id=HOTEL_ID,
            month=URL_MONTH,
        )

        out_dir = Path("workshop-runs")
        out_dir.mkdir(exist_ok=True)

        json_path = out_dir / "parity-list-export.json"
        json_path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
        print(f"Wrote {json_path} ({len(records)} rows)")

        if records:
            csv_path = out_dir / "parity-list-export.csv"
            keys = sorted({k for r in records for k in r})
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(records)
            print(f"Wrote {csv_path}")

            sample = next((r for r in records if "17/09" in str(r.get("date_label", ""))), records[0])
            print("\n=== Sample row ===")
            for k, v in sorted(sample.items()):
                if v and str(v).strip():
                    print(f"  {k}: {v}")
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
