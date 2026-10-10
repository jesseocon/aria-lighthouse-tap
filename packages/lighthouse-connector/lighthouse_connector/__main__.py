"""Local Lighthouse sync: `python -m lighthouse_connector sync <slug> [options]`."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from lighthouse_connector.runtime import project_root
from lighthouse_connector.local import connections_payload, registry_configs, sync_local


def _params(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if args.environment:
        params["environment"] = args.environment
    if args.start_date:
        params["start_date"] = args.start_date
    if args.end_date:
        params["end_date"] = args.end_date
    if args.keep_state:
        params["keep_state"] = True
    if args.scrape_only:
        params["scrape_only"] = True
    if args.transform_only:
        params["transform_only"] = True
    if args.test:
        params["dbt_test"] = True
    return params


def cmd_sync(args: argparse.Namespace) -> int:
    root = project_root()
    slugs = list(registry_configs(root, args.registry)) if args.all else [args.slug]
    if not slugs or slugs == [None]:
        raise SystemExit("Pass a slug or --all")
    for slug in slugs:
        if len(slugs) > 1:
            print(f"\n======== {slug} ========", flush=True)
        sync_local(root, slug, _params(args), registry_path=args.registry, dry_run=args.dry_run)
    return 0


def cmd_connections(args: argparse.Namespace) -> int:
    payload = json.dumps(connections_payload(project_root(), args.registry), indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(prog="lighthouse_connector")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "sync",
        help="Scrape once, copy bronze to production, dbt in both (or one --environment)",
    )
    p.add_argument("slug", nargs="?")
    p.add_argument("--all", action="store_true", help="Every property in the registry")
    p.add_argument("--environment", choices=["development", "production", "dev", "prod"])
    p.add_argument("--start-date")
    p.add_argument("--end-date")
    p.add_argument("--keep-state", action="store_true")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--scrape-only", action="store_true")
    mode.add_argument("--transform-only", action="store_true")
    p.add_argument("--test", action="store_true", help="dbt test after each run")
    p.add_argument("--registry", type=Path)
    p.add_argument("--dry-run", action="store_true", help="Print the commands only")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("connections", help="Registry rows as aria-runner connection JSON")
    p.add_argument("--registry", type=Path)
    p.add_argument("--out")
    p.set_defaults(func=cmd_connections)

    args = parser.parse_args(argv)
    if args.command == "sync" and bool(args.slug) == bool(args.all):
        parser.error("pass exactly one of <slug> or --all")
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
