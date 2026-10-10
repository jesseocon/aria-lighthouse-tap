#!/usr/bin/env python3
"""Emit dbt --vars JSON for a registry property and Meltano environment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from lighthouse_connector.properties import dbt_vars  # noqa: E402
from registry import (  # noqa: E402
    RegistryError,
    get_property,
    normalize_environment,
)

STRATEGY_SNAPSHOT_STREAM = "strategy-snapshot"


def _stream_name(pattern: str) -> str:
    return pattern.split(".", 1)[0].strip()


def _extractor_select(extractors: list, name: str = "tap-lighthouse") -> list[str] | None:
    for extractor in extractors:
        if extractor.get("name") != name:
            continue
        selected = extractor.get("select")
        if selected:
            return [str(pattern) for pattern in selected]
    return None


def strategy_snapshot_selected(
    environment: str,
    meltano_path: Path | None = None,
) -> bool:
    """True when this Meltano environment selects the strategy-snapshot stream."""
    path = meltano_path or (ROOT / "meltano.yml")
    project = yaml.safe_load(path.read_text())
    selected: list[str] | None = None
    for env in project.get("environments") or []:
        if env.get("name") != environment:
            continue
        extractors = (
            env.get("config", {}).get("plugins", {}).get("extractors") or []
        )
        selected = _extractor_select(extractors)
        break
    if selected is None:
        extractors = (project.get("plugins") or {}).get("extractors") or []
        selected = _extractor_select(extractors) or []
    return any(_stream_name(pattern) == STRATEGY_SNAPSHOT_STREAM for pattern in selected)


def build_dbt_vars(
    slug: str,
    environment: str,
    registry_path: Path | None = None,
    meltano_path: Path | None = None,
) -> dict:
    normalize_environment(environment)
    return dbt_vars(
        get_property(slug, registry_path),
        environment,
        include_strategy_snapshot=strategy_snapshot_selected(environment, meltano_path),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True, help="Property slug from registry.yml")
    parser.add_argument(
        "--environment",
        required=True,
        help="Meltano environment: development or production",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Optional path to registry.yml (defaults to config/properties/registry.yml)",
    )
    args = parser.parse_args()

    try:
        vars_payload = build_dbt_vars(args.slug, args.environment, args.registry)
    except RegistryError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(vars_payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
