"""dbt --vars helper tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dbt_vars_follow_meltano_environment() -> None:
    for environment, expected_property_id, expected_project in (
        ("production", "cmr9gjpz60001js046zkgomo9", "hospitalityops"),
        ("development", "cmrmb56w4000dbqu95a06jr1t", "hospitalityops-dev"),
    ):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "lib" / "dbt_vars.py"),
                "--slug",
                "hilton-garden-inn-boston-burlington",
                "--environment",
                environment,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout.strip())
        assert payload["property_id"] == expected_property_id
        assert payload["bq_project"] == expected_project
        assert payload["hotel_id"] == "202158"
        assert payload["include_strategy_snapshot"] is True
        assert "rate_shop_dimensions" not in payload
        assert "pivot_parent_group_slug" not in payload
