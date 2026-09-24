"""Tests for parity export helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tap_lighthouse.parity_export import (
    enrich_parity_records,
    normalize_field_name,
    parse_stay_date,
    parse_tooltip_text,
)
from tap_lighthouse.parity_months import (
    add_months,
    iter_months,
    resolve_parity_months,
    subtract_months,
)
from tap_lighthouse.parity_provenance import build_sync_params, hash_sync_params
from tap_lighthouse.parity_navigation import resolve_parity_list_url

FIXTURES = Path(__file__).parent / "fixtures" / "parity_tooltips.json"


@pytest.fixture
def tooltips() -> dict[str, str]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_normalize_field_name() -> None:
    assert normalize_field_name("brand.com") == "brand_com"
    assert normalize_field_name("Loss channels on metasearch") == "loss_channels_on_metasearch"


def test_parse_stay_date() -> None:
    assert parse_stay_date("Thu 17/09", "2026-09") == "2026-09-17"


def test_parse_rate_detail_tooltip(tooltips: dict[str, str]) -> None:
    parsed = parse_tooltip_text(tooltips["rate_detail"])
    assert parsed["tooltip_type"] == "rate_detail"
    assert parsed["hover_rate"] == "$ 179"
    assert "King Room" in parsed["hover_room_name"]


def test_parse_loss_channels_tooltip(tooltips: dict[str, str]) -> None:
    parsed = parse_tooltip_text(tooltips["loss_channels"])
    assert parsed["tooltip_type"] == "loss_channels"
    channels = parsed["hover_channels"]
    assert len(channels) == 2
    assert channels[0]["channel"] == "Hotelscombined"


def test_parse_simple_tooltip(tooltips: dict[str, str]) -> None:
    parsed = parse_tooltip_text(tooltips["sold_out"])
    assert parsed["tooltip_type"] == "simple"
    assert parsed["hover_text"] == "Sold out"


def test_enrich_parity_records_provenance() -> None:
    rows = [
        {
            "date_label": "Thu 17/09",
            "brand_com": "179",
            "brand_com_links": [{"text": "179", "href": "/redirect?ota=branddotcom"}],
            "column_7": "",
            "column_7_has_tooltip": False,
        },
    ]
    params = build_sync_params(
        hotel_id="202158",
        month="2026-09",
        los=1,
        max_persons=2,
        url="https://example.com",
    )
    params_hash = hash_sync_params(params)
    records = enrich_parity_records(
        rows,
        run_id="run-1",
        run_timestamp="2026-09-17T12:00:00+00:00",
        sync_params=params,
        sync_params_hash=params_hash,
        hotel_id="202158",
        month="2026-09",
    )
    record = records[0]
    assert record["run_id"] == "run-1"
    assert record["run_timestamp"] == "2026-09-17T12:00:00+00:00"
    assert record["sync_params_hash"] == params_hash
    assert record["stay_date"] == "2026-09-17"
    assert json.loads(record["sync_params"])["month"] == "2026-09"
    assert "column_7" not in record
    labels = json.loads(record["_parity_entity_labels"])
    assert labels["brand_com"] == "Brand.com"
    assert isinstance(record["brand_com_links"], str)
    assert json.loads(record["brand_com_links"])[0]["text"] == "179"


def test_resolve_parity_months() -> None:
    months = resolve_parity_months(as_of_month="2026-09", forward_months=2)
    assert months == ["2026-09", "2026-10", "2026-11"]


def test_resolve_parity_months_current_only() -> None:
    months = resolve_parity_months(as_of_month="2026-12", forward_months=0)
    assert months == ["2026-12"]


def test_iter_and_shift_months() -> None:
    assert iter_months("2026-11", "2027-01") == ["2026-11", "2026-12", "2027-01"]
    assert subtract_months("2026-09", 2) == "2026-07"
    assert add_months("2026-11", 2) == "2027-01"


def test_resolve_parity_list_url() -> None:
    url = resolve_parity_list_url("202158", los=1, max_persons=2, month="2026-09")
    assert "hotel/202158/parity/list" in url
    assert "month=2026-09" in url
