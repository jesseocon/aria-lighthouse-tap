"""Regression checks against a captured strategy-snapshot sync output."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "strategy-snapshot-example.jsonl"

REQUIRED_KEYS = frozenset(
    {
        "as_of_date",
        "record_hash",
        "as_of_date_date",
        "on_the_books",
        "on_the_books_adr",
        "_hotel_id",
        "_as_of_date",
        "_day_by_day_view",
        "_hierarchy",
    }
)

RATE_SHOP_PREFIX = (
    "rate_shop_powered_by_rate_insight_brand_com_bar_1_los_2_guests_"
    "hilton_garden_inn_boston_burlington_rate"
)


def _load_fixture() -> list[dict[str, str]]:
    return [
        json.loads(line)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_strategy_snapshot_example_fixture_exists() -> None:
    assert FIXTURE.is_file()


def test_strategy_snapshot_example_row_counts() -> None:
    rows = _load_fixture()
    by_as_of = Counter(row["as_of_date"] for row in rows)

    assert len(rows) == 730
    assert by_as_of == Counter({"2026-09-15": 365, "2026-09-16": 365})


def test_strategy_snapshot_example_schema_shape() -> None:
    rows = _load_fixture()
    field_counts = Counter(len(row) for row in rows)

    assert field_counts == Counter({60: 730})
    assert all(REQUIRED_KEYS.issubset(row) for row in rows)
    assert all(RATE_SHOP_PREFIX in row for row in rows)
    assert len({row["record_hash"] for row in rows}) == len(rows)


def test_strategy_snapshot_example_first_rows_match_capture() -> None:
    rows = _load_fixture()
    by_as_of: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_as_of.setdefault(row["as_of_date"], []).append(row)

    sep_15 = by_as_of["2026-09-15"][0]
    assert sep_15["as_of_date_date"] == "9/15/26 Tue"
    assert sep_15["on_the_books"] == "180"
    assert sep_15["_hotel_id"] == "202158"
    assert sep_15["_as_of_date"] == "09/15/2026"

    sep_16 = by_as_of["2026-09-16"][0]
    assert sep_16["as_of_date_date"] == "9/16/26 Wed"
    assert sep_16["on_the_books"] == "179"
    assert sep_16["_as_of_date"] == "09/16/2026"
