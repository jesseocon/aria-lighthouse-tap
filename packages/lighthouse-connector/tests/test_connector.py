from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from aria_runner.connectors import ConnectorManifest, load_connector, validate_params
from aria_runner.sdk import RunContext

from lighthouse_connector import runtime as lighthouse
from lighthouse_connector.local import connections_payload, registry_configs
from lighthouse_connector.manifest import manifest
from lighthouse_connector.plan import PlanError, build_plan
from lighthouse_connector.sync import MeltanoSync, RecordCounter

ROOT = Path(__file__).resolve().parents[3]
SLUG = "hilton-garden-inn-boston-burlington"


@pytest.fixture
def config() -> dict[str, Any]:
    return registry_configs(ROOT)[SLUG]


def _args(argv: list[str]) -> list[str]:
    return ["meltano", *argv[1:]]


def test_manifest_is_valid_and_registered() -> None:
    parsed = ConnectorManifest.model_validate(manifest())
    assert parsed.key == "lighthouse"
    assert parsed.session_required({"transform_only": False})
    assert not parsed.session_required({"transform_only": True})
    assert load_connector("lighthouse").key == "lighthouse"


def test_registry_rows_are_valid_connection_configs(config: dict[str, Any]) -> None:
    assert config["hotel_id"] == "202158"
    assert config["environments"] == ["development", "production"]
    assert config["tap"]["rates_rate_types"] == ["best_flex"]


def test_connections_payload_uses_meltano_selection() -> None:
    [row] = connections_payload(ROOT)
    assert row["id"] == SLUG and row["connector_key"] == "lighthouse"
    assert set(row["config"]["streams"]) >= {"rates", "strategy-snapshot"}


def test_default_plan_scrapes_once_copies_and_transforms_both(config, tmp_path: Path) -> None:  # noqa: ANN001
    plan = build_plan(config, {}, slug=SLUG, session_path=tmp_path / "s.json")
    assert plan.scrape_env == "development"
    assert plan.target_envs == ["development", "production"]
    assert plan.state_id == f"development:tap-lighthouse-to-target-bigquery:{SLUG}"
    assert _args(plan.scrape.argv) == [
        "meltano", "--environment=development", "run", "--state-id-suffix", SLUG,
        "lighthouse-scrape-bigquery",
    ]
    env = plan.scrape.env
    assert env["TAP_LIGHTHOUSE_HOTEL_ID"] == "202158"
    assert env["TAP_LIGHTHOUSE_STORAGE_STATE_PATH"] == str(tmp_path / "s.json")
    assert json.loads(env["TAP_LIGHTHOUSE__SELECT"]) == ["strategy-snapshot.*", "rates.*"]
    assert env["TAP_LIGHTHOUSE_RATES_RATE_TYPES"] == "best_flex"
    assert env["TAP_LIGHTHOUSE_RATES_REFRESH"] == "true"
    assert env["TARGET_BIGQUERY_PROJECT"] == "hospitalityops-dev"
    assert env["TARGET_BIGQUERY_DATASET"] == "bronze_1782243883257222643"
    maps = json.loads(env["TARGET_BIGQUERY_STREAM_MAPS"])
    assert maps["rates"] == {"__alias__": "mlt_lighthouse_ota__rates_hotel_202158"}

    spec = json.loads(plan.copy_bronze.argv[-1])
    assert spec["source_project"] == "hospitalityops-dev"
    assert spec["dest_project"] == "hospitalityops"
    assert "mlt_lighthouse_ota__rates_hotel_202158" in spec["tables"]

    names = [c.name for c in plan.transforms]
    assert names == ["dbt run (development)", "dbt run (production)"]
    prod_vars = json.loads(plan.transforms[1].argv[-1])
    assert prod_vars["property_id"] == "cmr9gjpz60001js046zkgomo9"
    assert prod_vars["property_slug"] == SLUG
    assert prod_vars["include_strategy_snapshot"] is True
    assert plan.transforms[1].env["DBT_BIGQUERY_PROJECT"] == "hospitalityops"


def test_single_environment_skips_copy(config) -> None:  # noqa: ANN001
    plan = build_plan(config, {"environment": "production", "dbt_test": True}, slug=SLUG)
    assert plan.scrape_env == "production"
    assert plan.copy_bronze is None
    assert [c.name for c in plan.transforms] == ["dbt run (production)", "dbt test (production)"]


def test_transform_only_and_backfill(config) -> None:  # noqa: ANN001
    plan = build_plan(config, {"transform_only": True}, slug=SLUG)
    assert plan.scrape is None and plan.copy_bronze is not None

    plan = build_plan(config, {"start_date": "2026-01-01", "end_date": "2026-01-31"}, slug=SLUG)
    assert plan.reset_state
    assert plan.scrape.env["TAP_LIGHTHOUSE_START_DATE"] == "2026-01-01"
    assert not build_plan(config, {"start_date": "2026-01-01", "keep_state": True}, slug=SLUG).reset_state
    with pytest.raises(PlanError):
        build_plan(config, {"start_date": "2026-02-01", "end_date": "2026-01-01"}, slug=SLUG)
    with pytest.raises(PlanError, match="end_date requires start_date"):
        build_plan(config, {"end_date": "2026-01-31"}, slug=SLUG)

    plan = build_plan(config, {"start_date": "2026-01-01"}, slug=SLUG)
    assert plan.reset_state
    assert plan.scrape.env["TAP_LIGHTHOUSE_START_DATE"] == "2026-01-01"
    assert plan.scrape.env["TAP_LIGHTHOUSE_END_DATE"] == "__UNSET__"


def test_params_schema_requires_start_with_end() -> None:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(manifest()["run_params_schema"])
    assert not list(validator.iter_errors({"start_date": "2026-01-01"}))
    assert not list(validator.iter_errors({"start_date": "2026-01-01", "end_date": "2026-01-31"}))
    assert list(validator.iter_errors({"end_date": "2026-01-31"}))


def test_params_schema_rejects_conflicting_modes() -> None:
    parsed = ConnectorManifest.model_validate(manifest())
    with pytest.raises(ValueError):
        validate_params(parsed, {"scrape_only": True, "transform_only": True})


class FakeRunner:
    def __init__(self, state_out: str = "") -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.state_out = state_out

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        cwd: Path,
        on_line: Callable[[str], None] | None = None,
    ) -> None:
        self.calls.append((_args(list(argv)), dict(env)))
        if on_line is not None and "run" in argv:
            on_line('INFO METRIC: {"type": "counter", "metric": "record_count", "value": 3, '
                    '"tags": {"stream": "rates"}}')

    def output(self, argv: Sequence[str], *, env: Mapping[str, str], cwd: Path) -> str:
        self.calls.append((_args(list(argv)), dict(env)))
        return self.state_out


def test_runner_seeds_and_reads_back_state(config, tmp_path: Path) -> None:  # noqa: ANN001
    runner = FakeRunner(state_out='{"singer_state": {"bookmarks": {"rates": 2}}}')
    sync = MeltanoSync(ROOT, runner, base_env={"PATH": "/bin"}, system_db_uri="sqlite:///x.db")
    plan = build_plan(config, {}, slug=SLUG)
    state, metrics = sync.execute(
        plan, prior_state={"singer_state": {"bookmarks": {"rates": 1}}}, manage_state=True
    )
    commands = [" ".join(c[0][:5]) for c in runner.calls]
    assert commands[0].startswith("meltano --environment=development state set --force")
    assert commands[1].startswith("meltano --environment=development run")
    assert commands[2].startswith("meltano --environment=development state get")
    assert "run-operation" in runner.calls[3][0][3]
    assert state == {"singer_state": {"bookmarks": {"rates": 2}}}
    assert metrics["records"] == {"rates": 3}
    scrape_env = runner.calls[1][1]
    assert scrape_env["MELTANO_DATABASE_URI"] == "sqlite:///x.db"
    assert scrape_env["DBT_BIGQUERY_AUTH_METHOD"] == "oauth"
    assert "TAP_LIGHTHOUSE_START_DATE" not in scrape_env


def test_backfill_does_not_seed_state(config) -> None:  # noqa: ANN001
    runner = FakeRunner()
    sync = MeltanoSync(ROOT, runner, base_env={"TAP_LIGHTHOUSE_END_DATE": "stale"})
    plan = build_plan(config, {"start_date": "2026-01-01", "environment": "development"}, slug=SLUG)
    sync.execute(plan, prior_state={"singer_state": {}}, manage_state=True)
    assert "state set" not in " ".join(runner.calls[0][0])
    assert "TAP_LIGHTHOUSE_END_DATE" not in runner.calls[0][1]


def test_record_counter_ignores_other_metrics() -> None:
    counter = RecordCounter()
    counter.observe('METRIC: {"metric": "http_request_duration", "value": 1}')
    counter.observe('METRIC: {"metric": "record_count", "value": 2, "tags": {"stream": "b"}}')
    counter.observe('METRIC: {"metric": "record_count", "value": 5, "tags": {"stream": "b"}}')
    assert counter.records == {"b": 7}


def test_connector_run_keeps_state_per_scrape_environment(config, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    runner = FakeRunner(state_out='{"singer_state": {"bookmarks": {"x": 1}}}')
    monkeypatch.setattr(lighthouse, "ContextRunner", lambda _ctx: runner)
    monkeypatch.setenv("MELTANO_PROJECT_ROOT", str(ROOT))
    ctx = RunContext(
        run_id="r",
        org_id="o",
        connection_id=SLUG,
        connector_key="lighthouse",
        config=config,
        params={},
        state={"production": {"singer_state": {}}},
        work_dir=tmp_path,
        session_path=tmp_path / "s.json",
        logger=logging.getLogger("t"),
    )
    result = lighthouse.LighthouseConnector().run(ctx)
    assert result.state == {
        "production": {"singer_state": {}},
        "development": {"singer_state": {"bookmarks": {"x": 1}}},
    }
    assert result.metrics["records"] == {"rates": 3}
