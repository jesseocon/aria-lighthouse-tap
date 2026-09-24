#!/usr/bin/env python3
"""Print registry fields for shell wrappers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from registry import (  # noqa: E402
    RegistryError,
    bronze_budget_table,
    bronze_forecast_table,
    bronze_parity_list_table,
    bronze_snapshot_daily_table,
    get_property,
)


def build_stream_maps(prop: dict) -> dict[str, dict[str, str]]:
    source = str(prop["source"])
    hotel_id = str(prop["hotel_id"])
    return {
        "strategy-snapshot": {
            "__alias__": bronze_snapshot_daily_table(source, hotel_id),
        },
        "parity-list": {
            "__alias__": bronze_parity_list_table(source, hotel_id),
        },
        "budget": {
            "__alias__": bronze_budget_table(source, hotel_id),
        },
        "forecast": {
            "__alias__": bronze_forecast_table(source, hotel_id),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument(
        "--field",
        choices=(
            "hotel_id",
            "bronze_table",
            "bronze_parity_table",
            "bronze_budget_table",
            "bronze_forecast_table",
            "stream_maps",
            "json",
        ),
        default="json",
    )
    parser.add_argument("--registry", type=Path, default=None)
    args = parser.parse_args()

    try:
        prop = get_property(args.slug, args.registry)
    except RegistryError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    source = str(prop["source"])
    hotel_id = str(prop["hotel_id"])

    if args.field == "hotel_id":
        print(hotel_id)
    elif args.field == "bronze_table":
        print(bronze_snapshot_daily_table(source, hotel_id))
    elif args.field == "bronze_parity_table":
        print(bronze_parity_list_table(source, hotel_id))
    elif args.field == "bronze_budget_table":
        print(bronze_budget_table(source, hotel_id))
    elif args.field == "bronze_forecast_table":
        print(bronze_forecast_table(source, hotel_id))
    elif args.field == "stream_maps":
        print(json.dumps(build_stream_maps(prop), separators=(",", ":")))
    else:
        print(
            json.dumps(
                {
                    "slug": prop["slug"],
                    "hotel_id": hotel_id,
                    "bronze_table": bronze_snapshot_daily_table(source, hotel_id),
                    "bronze_parity_table": bronze_parity_list_table(source, hotel_id),
                    "bronze_budget_table": bronze_budget_table(source, hotel_id),
                    "bronze_forecast_table": bronze_forecast_table(source, hotel_id),
                    "stream_maps": build_stream_maps(prop),
                },
                separators=(",", ":"),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
