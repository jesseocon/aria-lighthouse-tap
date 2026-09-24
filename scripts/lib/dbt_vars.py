#!/usr/bin/env python3
"""Emit dbt --vars JSON for a registry property and tier."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from registry import RegistryError, get_property, property_id_for_tier  # noqa: E402


def build_dbt_vars(slug: str, tier: str, registry_path: Path | None = None) -> dict:
    prop = get_property(slug, registry_path)
    return {
        "bq_project": prop["bq_project"],
        "org_id": prop["org_id"],
        "source": prop["source"],
        "property_id": property_id_for_tier(prop, tier),
        "property_slug": prop.get("property_slug") or prop["slug"],
        "hotel_id": str(prop["hotel_id"]),
        "subject_entity_key": prop["subject_entity_key"],
        "pivot_parent_group_slug": prop["pivot_parent_group_slug"],
        "rate_shop_dimensions": prop["rate_shop_dimensions"],
        "parity_channel_dimensions": prop["parity_channel_dimensions"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True, help="Property slug from registry.yml")
    parser.add_argument(
        "--tier",
        required=True,
        choices=("prod", "dev"),
        help="Aria property tier to stamp on silver/gold tables",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Optional path to registry.yml (defaults to config/properties/registry.yml)",
    )
    args = parser.parse_args()

    try:
        vars_payload = build_dbt_vars(args.slug, args.tier, args.registry)
    except RegistryError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(vars_payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
