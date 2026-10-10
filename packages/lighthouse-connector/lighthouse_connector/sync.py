"""Execute a SyncPlan with Meltano subprocesses. No shell, no sourced env files."""

from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from lighthouse_connector.plan import Command, SyncPlan, meltano, merge_env

log = logging.getLogger(__name__)

METRIC_PATTERN = re.compile(r"METRIC: (\{.*\})")


class Runner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        cwd: Path,
        on_line: Callable[[str], None] | None = None,
    ) -> None: ...

    def output(self, argv: Sequence[str], *, env: Mapping[str, str], cwd: Path) -> str: ...


@dataclass
class RecordCounter:
    """Sum Singer SDK record_count metrics per stream from tap log lines."""

    records: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def observe(self, line: str) -> None:
        match = METRIC_PATTERN.search(line)
        if not match:
            return
        try:
            metric = json.loads(match.group(1))
        except json.JSONDecodeError:
            return
        if metric.get("metric") != "record_count":
            return
        tags = metric.get("tags") or {}
        stream = str(tags.get("stream") or "unknown")
        self.records[stream] += int(metric.get("value") or 0)


def bigquery_auth_env(environ: Mapping[str, str]) -> dict[str, str]:
    """Key file when one is configured; otherwise Application Default Credentials."""
    env: dict[str, str] = {}
    keyfile = environ.get("DBT_BIGQUERY_KEYFILE") or environ.get("TARGET_BIGQUERY_CREDENTIALS_PATH")
    if keyfile:
        if not Path(keyfile).is_file():
            raise FileNotFoundError(f"GCP credentials file not found: {keyfile}")
        env["DBT_BIGQUERY_KEYFILE"] = keyfile
        env["DBT_BIGQUERY_AUTH_METHOD"] = environ.get("DBT_BIGQUERY_AUTH_METHOD", "service-account")
    else:
        env["DBT_BIGQUERY_AUTH_METHOD"] = environ.get("DBT_BIGQUERY_AUTH_METHOD", "oauth")
    return env


class MeltanoSync:
    def __init__(
        self,
        project_root: Path,
        runner: Runner,
        *,
        base_env: Mapping[str, str] | None = None,
        system_db_uri: str | None = None,
    ) -> None:
        self.project_root = project_root
        self.runner = runner
        env = dict(base_env if base_env is not None else os.environ)
        env["MELTANO_PROJECT_ROOT"] = str(project_root)
        env.pop("VIRTUAL_ENV", None)
        if system_db_uri:
            env["MELTANO_DATABASE_URI"] = system_db_uri
        env.update(bigquery_auth_env(env))
        self.base_env = env

    def _env(self, command: Command) -> dict[str, str]:
        return merge_env(self.base_env, command.env)

    def _run(self, command: Command, on_line: Callable[[str], None] | None = None) -> None:
        log.info("==> %s", command.name)
        self.runner.run(command.argv, env=self._env(command), cwd=self.project_root, on_line=on_line)

    def get_state(self, plan: SyncPlan) -> dict[str, Any] | None:
        out = self.runner.output(
            meltano(plan.scrape_env, "state", "get", plan.state_id),
            env=self.base_env,
            cwd=self.project_root,
        ).strip()
        if not out:
            return None
        start = out.find("{")
        return (json.loads(out[start:]) or None) if start >= 0 else None

    def set_state(self, plan: SyncPlan, state: dict[str, Any]) -> None:
        self.runner.run(
            meltano(plan.scrape_env, "state", "set", "--force", plan.state_id, json.dumps(state)),
            env=self.base_env,
            cwd=self.project_root,
        )

    def clear_state(self, plan: SyncPlan) -> None:
        self.runner.run(
            meltano(plan.scrape_env, "state", "clear", "--force", plan.state_id),
            env=self.base_env,
            cwd=self.project_root,
        )

    def execute(
        self,
        plan: SyncPlan,
        *,
        prior_state: dict[str, Any] | None,
        manage_state: bool,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Run the plan. Returns (singer state after the scrape, metrics).

        manage_state=True: the caller owns bookmarks (runner). We seed Meltano's throwaway
        system database before the scrape and read the result back afterwards.
        manage_state=False: Meltano's project database owns bookmarks (local runs).
        """
        metrics: dict[str, Any] = {
            "scrape_environment": plan.scrape_env,
            "target_environments": plan.target_envs,
            "steps": [],
        }
        new_state: dict[str, Any] | None = None

        if plan.scrape is not None:
            if plan.reset_state:
                log.info("==> date-range backfill: starting %s from empty state", plan.slug)
                if not manage_state:
                    self.clear_state(plan)
            elif manage_state and prior_state:
                self.set_state(plan, prior_state)
            counter = RecordCounter()
            self._run(plan.scrape, counter.observe)
            metrics["steps"].append(plan.scrape.name)
            metrics["records"] = dict(counter.records)
            if manage_state:
                new_state = self.get_state(plan)

        if plan.copy_bronze is not None:
            self._run(plan.copy_bronze)
            metrics["steps"].append(plan.copy_bronze.name)

        for command in plan.transforms:
            self._run(command)
            metrics["steps"].append(command.name)

        return new_state, metrics
