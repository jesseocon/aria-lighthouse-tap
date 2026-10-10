"""Local runs from config/properties/registry.yml (the workshop path, no control plane)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from aria_runner.connectors import ConnectorManifest, validate_config

from lighthouse_connector.manifest import KEY, manifest
from lighthouse_connector.plan import SyncPlan, build_plan, meltano
from lighthouse_connector.properties import ENVIRONMENTS, STRATEGY_SNAPSHOT_STREAM
from lighthouse_connector.sync import MeltanoSync

log = logging.getLogger(__name__)

REGISTRY = Path("config/properties/registry.yml")
LEGACY_STATE_JOB = "tap-lighthouse-to-target-bigquery"


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def local_environ(root: Path) -> dict[str, str]:
    """os.environ wins over .env.local, which wins over .env."""
    merged: dict[str, str] = {}
    for name in (".env", ".env.local"):
        merged.update(read_env_file(root / name))
    merged.update(os.environ)
    return merged


def registry_configs(root: Path, registry_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Registry rows as validated connection configs, keyed by slug."""
    data = yaml.safe_load((registry_path or root / REGISTRY).read_text(encoding="utf-8"))
    shared = {"org_id": data["org_id"]}
    schema = ConnectorManifest.model_validate(manifest())
    configs: dict[str, dict[str, Any]] = {}
    for prop in data["properties"]:
        config = {**shared, **prop}
        config.pop("slug", None)
        config.pop("property_slug", None)
        config.pop("subject_entity_key", None)
        config.pop("pivot_parent_group_slug", None)
        config.pop("rate_shop_dimensions", None)
        config.pop("parity_channel_dimensions", None)
        config["hotel_id"] = str(config["hotel_id"])
        configs[str(prop["slug"])] = validate_config(schema, config)
    return configs


def meltano_selected_streams(root: Path, environment: str) -> list[str]:
    project = yaml.safe_load((root / "meltano.yml").read_text(encoding="utf-8"))

    def select_of(extractors: list[dict[str, Any]]) -> list[str] | None:
        for extractor in extractors or []:
            if extractor.get("name") == "tap-lighthouse" and extractor.get("select"):
                return [str(pattern).split(".", 1)[0] for pattern in extractor["select"]]
        return None

    for env in project.get("environments") or []:
        if env.get("name") == environment:
            found = select_of(env.get("config", {}).get("plugins", {}).get("extractors"))
            if found is not None:
                return found
    return select_of((project.get("plugins") or {}).get("extractors")) or []


def connections_payload(root: Path, registry_path: Path | None = None) -> list[dict[str, Any]]:
    """Registry → `aria_runner connections put --file` payload."""
    selected = sorted(
        {s for env in ENVIRONMENTS for s in meltano_selected_streams(root, env)}
    )
    out = []
    for slug, config in registry_configs(root, registry_path).items():
        out.append(
            {
                "id": slug,
                "connector_key": KEY,
                "name": slug,
                "config": {**config, "streams": selected or config["streams"]},
            }
        )
    return out


class LocalRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        cwd: Path,
        on_line: Callable[[str], None] | None = None,
    ) -> None:
        proc = subprocess.Popen(
            list(argv),
            env=dict(env),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            if on_line is not None:
                on_line(line)
        if proc.wait() != 0:
            raise subprocess.CalledProcessError(proc.returncode, argv[:4])

    def output(self, argv: Sequence[str], *, env: Mapping[str, str], cwd: Path) -> str:
        return subprocess.run(
            list(argv), env=dict(env), cwd=cwd, check=True, capture_output=True, text=True
        ).stdout


def adopt_legacy_state(sync: MeltanoSync, plan: SyncPlan, root: Path) -> None:
    """Bookmarks used to live under one unsuffixed id per environment; move them once."""
    marker = root / ".meltano" / f"last-scrape-slug-{plan.scrape_env}"
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != plan.slug:
        return
    if sync.get_state(plan):
        return
    legacy = f"{plan.scrape_env}:{LEGACY_STATE_JOB}"
    try:
        sync.runner.run(
            meltano(plan.scrape_env, "state", "copy", "--force", legacy, plan.state_id),
            env=sync.base_env,
            cwd=root,
        )
        log.info("adopted bookmarks %s → %s", legacy, plan.state_id)
    except subprocess.CalledProcessError:
        log.info("no legacy bookmarks at %s", legacy)
    marker.unlink(missing_ok=True)


def sync_local(
    root: Path,
    slug: str,
    params: dict[str, Any],
    *,
    registry_path: Path | None = None,
    dry_run: bool = False,
) -> int:
    configs = registry_configs(root, registry_path)
    if slug not in configs:
        raise SystemExit(f"Unknown property slug: {slug} (known: {', '.join(configs)})")
    # meltano.yml keeps owning stream selection and tap settings for local runs.
    config = {k: v for k, v in configs[slug].items() if k not in ("streams", "tap")}
    plan = build_plan(
        config,
        params,
        slug=slug,
        strategy_snapshot_by_env={
            env: STRATEGY_SNAPSHOT_STREAM in meltano_selected_streams(root, env)
            for env in ENVIRONMENTS
        },
    )
    if dry_run:
        for command in (plan.scrape, plan.copy_bronze, *plan.transforms):
            if command is not None:
                print(json.dumps({"name": command.name, "argv": ["meltano", *command.argv[1:]],
                                  "env": command.env}, indent=2))
        return 0
    sync = MeltanoSync(root, LocalRunner(), base_env=local_environ(root))
    if plan.scrape is not None:
        adopt_legacy_state(sync, plan, root)
    _, metrics = sync.execute(plan, prior_state=None, manage_state=False)
    print(f"==> Done: {slug} {json.dumps(metrics.get('records', {}))}")
    return 0
