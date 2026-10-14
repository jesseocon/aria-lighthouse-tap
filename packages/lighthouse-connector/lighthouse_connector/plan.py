"""One property sync as data: which environments, which env vars, which Meltano commands."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from lighthouse_connector import properties as p
from lighthouse_connector.manifest import LOGIN_URL

EXTRACTOR_ENV = "TAP_LIGHTHOUSE"
STATE_JOB = "tap-lighthouse-to-target-bigquery"
SCRAPE_JOB = "lighthouse-scrape-bigquery"

_UNSET = "__UNSET__"


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class RunOptions:
    environment: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    keep_state: bool = False
    scrape: bool = True
    transform: bool = True
    dbt_test: bool | None = None

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RunOptions:
        if params.get("scrape_only") and params.get("transform_only"):
            raise PlanError("scrape_only and transform_only are mutually exclusive")
        options = cls(
            environment=p.normalize_environment(params["environment"])
            if params.get("environment")
            else None,
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
            keep_state=bool(params.get("keep_state", False)),
            scrape=not params.get("transform_only", False),
            transform=not params.get("scrape_only", False),
            dbt_test=params.get("dbt_test"),
        )
        for label, value in (("start_date", options.start_date), ("end_date", options.end_date)):
            if value is not None:
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise PlanError(f"{label} must be YYYY-MM-DD, got {value!r}") from exc
        if options.end_date and not options.start_date:
            raise PlanError("end_date requires start_date")
        if options.start_date and options.end_date and options.start_date > options.end_date:
            raise PlanError(
                f"start_date ({options.start_date}) must be on or before end_date "
                f"({options.end_date})"
            )
        return options

    @property
    def backfill(self) -> bool:
        return bool(self.start_date or self.end_date)

    @property
    def reset_state(self) -> bool:
        return self.backfill and not self.keep_state


@dataclass
class Command:
    name: str
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class SyncPlan:
    slug: str
    scrape_env: str
    target_envs: list[str]
    state_id: str
    reset_state: bool
    scrape: Command | None
    copy_bronze: Command | None
    transforms: list[Command]


def meltano_executable() -> str:
    """The meltano console script installed next to this interpreter."""
    candidate = Path(sys.executable).with_name("meltano")
    return str(candidate) if candidate.exists() else "meltano"


def meltano(environment: str, *args: str) -> list[str]:
    return [meltano_executable(), f"--environment={environment}", *args]


def property_from_config(config: dict[str, Any], *, slug: str) -> dict[str, Any]:
    prop = {
        k: v
        for k, v in config.items()
        if k not in ("streams", "environments", "tap", "slug", "property_slug")
    }
    prop["slug"] = slug
    prop["property_slug"] = slug
    prop.setdefault("source", p.DEFAULT_SOURCE)
    prop.setdefault("bq_project_development", p.DEFAULT_BQ_PROJECT_DEVELOPMENT)
    prop.setdefault("bq_project_production", p.DEFAULT_BQ_PROJECT_PRODUCTION)
    return prop


def target_environments(config: dict[str, Any], options: RunOptions) -> tuple[str, list[str]]:
    allowed = [p.normalize_environment(e) for e in config.get("environments") or p.ENVIRONMENTS]
    if options.environment:
        if options.environment not in allowed:
            raise PlanError(f"{options.environment} is not enabled for this connection")
        return options.environment, [options.environment]
    targets = [e for e in p.ENVIRONMENTS if e in allowed]
    return targets[0], targets


def state_id(environment: str, slug: str) -> str:
    return f"{environment}:{STATE_JOB}:{slug}"


def _setting_env(name: str) -> str:
    return f"{EXTRACTOR_ENV}_{name.upper()}"


def tap_env(
    config: dict[str, Any],
    prop: dict[str, Any],
    options: RunOptions,
    scrape_env: str,
    session_path: Path | None,
    secret_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env: dict[str, str] = {
        _setting_env("hotel_id"): str(prop["hotel_id"]),
        "TARGET_BIGQUERY_PROJECT": p.bq_project_for_environment(prop, scrape_env),
        "TARGET_BIGQUERY_DATASET": p.bronze_dataset(str(prop["org_id"])),
        "TARGET_BIGQUERY_STREAM_MAPS": json.dumps(p.stream_maps(prop), separators=(",", ":")),
        _setting_env("start_date"): options.start_date or _UNSET,
        _setting_env("end_date"): options.end_date or _UNSET,
    }
    if config.get("streams"):
        env[f"{EXTRACTOR_ENV}__SELECT"] = json.dumps([f"{s}.*" for s in config["streams"]])
    secrets = secret_env or {}
    username = secrets.get("TAP_LIGHTHOUSE_USERNAME")
    password = secrets.get("TAP_LIGHTHOUSE_PASSWORD")
    if username and password:
        env[_setting_env("auth_method")] = "password"
        env[_setting_env("login_url")] = LOGIN_URL
        env[_setting_env("username")] = username
        env[_setting_env("password")] = password
    elif session_path is not None:
        env[_setting_env("auth_method")] = "storage_state"
        env[_setting_env("storage_state_path")] = str(session_path)
    for name, value in (config.get("tap") or {}).items():
        if name == "start_date" and options.start_date:
            continue
        if isinstance(value, list):
            value = ",".join(str(v) for v in value)
        elif isinstance(value, bool):
            value = "true" if value else "false"
        env[_setting_env(name)] = str(value)
    if not options.start_date and (config.get("tap") or {}).get("start_date"):
        env[_setting_env("start_date")] = str(config["tap"]["start_date"])
    if username and password:
        env[_setting_env("headless")] = "false"
    return env


def dbt_env(prop: dict[str, Any], environment: str) -> dict[str, str]:
    return {
        "MELTANO_ENVIRONMENT": environment,
        "DBT_BIGQUERY_PROJECT": p.bq_project_for_environment(prop, environment),
        "DBT_BIGQUERY_DATASET": p.silver_dataset(str(prop["org_id"])),
    }


def build_plan(
    config: dict[str, Any],
    params: dict[str, Any],
    *,
    slug: str,
    session_path: Path | None = None,
    secret_env: dict[str, str] | None = None,
    strategy_snapshot_by_env: dict[str, bool] | None = None,
) -> SyncPlan:
    """Without `streams` in config, Meltano's own `select` applies and the caller says
    per environment whether strategy-snapshot bronze exists (strategy_snapshot_by_env)."""
    options = RunOptions.from_params(params)
    prop = property_from_config(config, slug=slug)
    scrape_env, targets = target_environments(config, options)
    streams = list(config.get("streams") or [])
    run_tests = config.get("dbt_test", False) if options.dbt_test is None else options.dbt_test

    scrape = None
    if options.scrape:
        scrape = Command(
            name=f"scrape {slug} ({scrape_env})",
            argv=meltano(scrape_env, "run", "--state-id-suffix", slug, SCRAPE_JOB),
            env=tap_env(config, prop, options, scrape_env, session_path, secret_env),
        )

    copy_bronze = None
    if len(targets) == 2:
        copy_bronze = Command(
            name="copy bronze development → production",
            argv=meltano(
                "development",
                "invoke",
                "dbt-bigquery:run-operation",
                "copy_bronze_tables",
                "--args",
                json.dumps(p.bronze_copy_spec(prop), separators=(",", ":")),
            ),
            env=dbt_env(prop, "development"),
        )

    transforms: list[Command] = []
    if options.transform:
        for env in targets:
            if strategy_snapshot_by_env is not None:
                include_snapshot = strategy_snapshot_by_env.get(env, False)
            else:
                include_snapshot = p.STRATEGY_SNAPSHOT_STREAM in streams
            dbt_args = json.dumps(
                p.dbt_vars(prop, env, include_strategy_snapshot=include_snapshot),
                separators=(",", ":"),
            )
            transforms.append(
                Command(
                    name=f"dbt run ({env})",
                    argv=meltano(env, "invoke", "dbt-bigquery:run", "--vars", dbt_args),
                    env=dbt_env(prop, env),
                )
            )
            if run_tests:
                transforms.append(
                    Command(
                        name=f"dbt test ({env})",
                        argv=meltano(env, "invoke", "dbt-bigquery:test", "--vars", dbt_args),
                        env=dbt_env(prop, env),
                    )
                )

    return SyncPlan(
        slug=slug,
        scrape_env=scrape_env,
        target_envs=targets,
        state_id=state_id(scrape_env, slug),
        reset_state=options.reset_state,
        scrape=scrape,
        copy_bronze=copy_bronze,
        transforms=transforms,
    )


def merge_env(base: dict[str, str], overrides: dict[str, str]) -> dict[str, str]:
    """Apply overrides; the _UNSET marker removes a variable inherited from the parent."""
    env = dict(base)
    for key, value in overrides.items():
        if value == _UNSET:
            env.pop(key, None)
        else:
            env[key] = value
    return env
