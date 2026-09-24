"""dbt --vars helper tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dbt_vars_emits_prod_and_dev_property_ids() -> None:
    for tier, expected_property_id in (
        ("prod", "cmr9gjpz60001js046zkgomo9"),
        ("dev", "cmrmb56w4000dbqu95a06jr1t"),
    ):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "lib" / "dbt_vars.py"),
                "--slug",
                "hilton-garden-inn-boston-burlington",
                "--tier",
                tier,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout.strip())
        assert payload["property_id"] == expected_property_id
        assert payload["hotel_id"] == "202158"
        assert isinstance(payload["rate_shop_dimensions"], list)
