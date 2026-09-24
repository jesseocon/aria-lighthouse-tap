"""Meltano BigQuery / dbt wiring checks."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TRANSFORM = ROOT / "transform"
DBT = ROOT / ".meltano" / "utilities" / "dbt-bigquery" / "venv" / "bin" / "dbt"
PROPERTY_CONFIG = ROOT / "config" / "properties" / "development.yml"


def test_development_property_config_exists() -> None:
    data = yaml.safe_load(PROPERTY_CONFIG.read_text(encoding="utf-8"))
    assert data["property_id"] == "cmrmb56w4000dbqu95a06jr1t"
    assert data["source"] == "mlt_lighthouse_ota"
    assert "rate_shop_dimensions" in data
    assert data["bronze_table_snapshot_daily"] == (
        "mlt_lighthouse_ota__snapshot_daily_hotel_202158"
    )


def test_meltano_environments_include_local_and_development() -> None:
    meltano = yaml.safe_load((ROOT / "meltano.yml").read_text(encoding="utf-8"))
    env_names = {env["name"] for env in meltano["environments"]}
    assert env_names >= {"local", "development"}


def test_meltano_has_bigquery_loader_and_dbt_utility() -> None:
    meltano = yaml.safe_load((ROOT / "meltano.yml").read_text(encoding="utf-8"))
    loader_names = {loader["name"] for loader in meltano["plugins"]["loaders"]}
    utility_names = {utility["name"] for utility in meltano["plugins"]["utilities"]}
    assert "target-bigquery" in loader_names
    assert "dbt-bigquery" in utility_names


def test_meltano_jobs_include_scrape_and_transform() -> None:
    meltano = yaml.safe_load((ROOT / "meltano.yml").read_text(encoding="utf-8"))
    job_names = {job["name"] for job in meltano["jobs"]}
    assert "lighthouse-scrape-bigquery" in job_names
    assert "lighthouse-transform" in job_names
    assert "lighthouse-development-bigquery" in job_names


def test_development_env_has_no_hardcoded_bronze_alias() -> None:
    meltano = yaml.safe_load((ROOT / "meltano.yml").read_text(encoding="utf-8"))
    development = next(env for env in meltano["environments"] if env["name"] == "development")
    loader_cfg = next(
        plugin["config"]
        for plugin in development["config"]["plugins"]["loaders"]
        if plugin["name"] == "target-bigquery"
    )
    stream_maps = loader_cfg.get("stream_maps", {})
    assert "cmrmb56w4000dbqu95a06jr1t" not in str(stream_maps)


def test_dbt_project_parses() -> None:
    if not DBT.is_file():
        return
    env = {
        "MELTANO_ENVIRONMENT": "development",
        "TARGET_BIGQUERY_PROJECT": "hospitalityops",
        "ARIA_PROPERTY_ID": "cmrmb56w4000dbqu95a06jr1t",
        "ARIA_ORG_ID": "1782243883257222643",
        "ARIA_HOTEL_ID": "202158",
    }
    result = subprocess.run(
        [
            str(DBT),
            "parse",
            "--profiles-dir",
            str(TRANSFORM / "profiles" / "bigquery"),
            "--project-dir",
            str(TRANSFORM),
        ],
        cwd=TRANSFORM,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_dbt_gold_models_exist() -> None:
    marts = TRANSFORM / "models" / "marts"
    assert (marts / "mlt_mart_day_by_day_grid.sql").is_file()
    assert (marts / "mlt_mart_rate_shop_daily.sql").is_file()
    assert (marts / "mlt_mart_budget.sql").is_file()
