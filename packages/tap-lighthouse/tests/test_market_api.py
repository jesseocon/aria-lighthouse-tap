"""Market-context streams: request shapes match captured page calls; responses map to records.

Fixtures are trimmed from workshop run 20261029-220956-9401d156 (hotel 202158).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import jsonschema
import pytest

from tap_lighthouse.api_client import ApiClient, Pacer
from tap_lighthouse.lighthouse_api import HotelContext, parse_hotel_context
from tap_lighthouse.market_api import (
    app_primary_compset,
    build_demand_records,
    build_event_records,
    build_holiday_records,
    build_ranking_daily_records,
    build_ranking_summary_records,
    build_rate_strategy_records,
    build_smart_insight_records,
    demand_snapshot_request,
    holidays_request,
    market_events_request,
    ranking_daily_request,
    ranking_summary_request,
    rate_strategy_request,
    smart_insights_request,
    snapshot_week,
    week_offsets_to_fetch,
)
from tap_lighthouse.market_schemas import (
    build_demand_schema,
    build_events_schema,
    build_holidays_schema,
    build_ranking_daily_schema,
    build_ranking_summary_schema,
    build_rate_strategy_schema,
    build_smart_insights_schema,
)

FIXTURES = Path(__file__).parent / "fixtures" / "api"
BASE = "https://app.mylighthouse.com"
HOTEL = "202158"
SUBJECT = 28650
NOW = "2026-10-29T12:00:00-05:00"


def fixture(name: str) -> Any:  # noqa: ANN401
    return json.loads((FIXTURES / name).read_text())


def hotel_context() -> HotelContext:
    return parse_hotel_context(fixture("hotels.json"))


def query(url: str) -> tuple[str, list[tuple[str, str]]]:
    parts = urlsplit(url)
    return parts.path, parse_qsl(parts.query)


def valid(records: list[dict[str, Any]], schema: dict[str, Any]) -> None:
    assert records
    for record in records:
        jsonschema.validate(record, schema)
        assert set(record) <= set(schema["properties"]), set(record) - set(schema["properties"])


# --- request shapes (copied from captured page requests) ---


def test_events_page_requests_match_page() -> None:
    assert query(market_events_request(BASE, HOTEL, start_date="2026-09-28", end_date="2026-11-01").url) == (
        "/apigateway/v1/app/events/",
        [("hotel_id", HOTEL), ("from_date_range_start", "2026-09-28"), ("from_date_range_end", "2026-11-01")],
    )
    assert query(holidays_request(BASE, HOTEL, start_date="2026-09-28", end_date="2026-11-01").url) == (
        "/apigateway/v1/app/holidays/",
        [("from_date_range_start", "2026-09-28"), ("from_date_range_end", "2026-11-01"), ("hotel_id", HOTEL)],
    )
    assert query(demand_snapshot_request(BASE, HOTEL, start_date="2026-09-28", end_date="2026-11-01").url) == (
        "/apigateway/v1/app/demand/ari/demands/",
        [("subscription_id", HOTEL), ("from_date_range_start", "2026-09-28"), ("from_date_range_end", "2026-11-01")],
    )
    assert query(
        smart_insights_request(BASE, HOTEL, as_of_date="2026-10-29", rate_type="lowest", ota="bookingdotcom").url
    ) == (
        "/apigateway/v1/app/smartinsights/insights/",
        [
            ("subscription_id", HOTEL),
            ("extract_date", "2026-10-29"),
            ("from_date_start", "2026-10-29"),
            ("rate_type", "lowest"),
            ("ota", "bookingdotcom"),
            ("language", "en"),
        ],
    )


def test_ranking_and_strategy_requests_match_page() -> None:
    assert query(ranking_summary_request(BASE, HOTEL, granularity="monthly", compset_id=1).url) == (
        "/apigateway/v1/app/rankings/aggregated/",
        [("hotel_id", HOTEL), ("los", "1"), ("granularity", "monthly"), ("compset_ids", "1")],
    )
    assert query(ranking_daily_request(BASE, HOTEL, ota="bookingdotcom", compset_id=1).url) == (
        "/apigateway/v1/app/rankings/",
        [
            ("ota", "bookingdotcom"),
            ("hotel_id", HOTEL),
            ("los", "1"),
            ("data", "ranking"),
            ("compset_ids", "1"),
            ("meta", "nested"),
        ],
    )
    assert query(rate_strategy_request(BASE, HOTEL, compset_id=1, week_offsets=[-1, -4, -12]).url) == (
        "/apigateway/v1/app/ratestrategy/",
        [("hotel_id", HOTEL), ("compset_ids", "1"), ("weeks[]", "-1"), ("weeks[]", "-4"), ("weeks[]", "-12")],
    )


def test_app_primary_compset_is_found_by_name() -> None:
    hotel = hotel_context()
    assert hotel.compset_names.get("1") == "App Primary"
    assert app_primary_compset(hotel) == 1
    renamed = HotelContext(subject_hotelinfo_id=SUBJECT, spider_id=None, hotelinfos={}, compset_names={"7": "App Primary"})
    assert app_primary_compset(renamed) == 7
    assert app_primary_compset(HotelContext(subject_hotelinfo_id=SUBJECT, spider_id=None, hotelinfos={})) == 1


# --- records ---


def test_event_records() -> None:
    records = build_event_records(fixture("market_events.json"), hotel_id=HOTEL, extracted_at=NOW)
    valid(records, build_events_schema())
    first = records[0]
    assert first["hotel_id"] == HOTEL and first["event_id"]
    assert first["category"] == "conference" and first["status"] == "accepted"
    assert first["days"] == ["2026-09-30"] and first["labels"] == ["business", "conference"]
    assert first["max_distance"] == 30


def test_holiday_records() -> None:
    records = build_holiday_records(fixture("holidays.json"), hotel_id=HOTEL, extracted_at=NOW)
    valid(records, build_holidays_schema())
    assert records[0]["name"] == "Columbus Day (Regional Holiday)"
    assert records[0]["countries"] == ["us"] and records[0]["subscriptions"] == [202158]


def test_demand_drops_days_outside_the_horizon() -> None:
    payload = fixture("demand_snapshot.json")
    assert any(d["message"] for d in payload["demands"])
    records = build_demand_records(payload, hotel_id=HOTEL, as_of_date="2026-10-29", extracted_at=NOW)
    valid(records, build_demand_schema())
    assert len(records) == 3
    assert all(0 < r["demand_index"] <= 1 and r["as_of_date"] == "2026-10-29" for r in records)


def test_smart_insights_flatten_kpis_and_keep_unknown_ones() -> None:
    payload = fixture("smart_insights.json")
    payload["insights"][0]["kpis"]["brand_new_kpi"] = 1.5
    records = build_smart_insight_records(
        payload, hotel_id=HOTEL, as_of_date="2026-10-29", rate_type="lowest", ota="bookingdotcom", extracted_at=NOW
    )
    valid(records, build_smart_insights_schema())
    first = records[0]
    assert first["stay_date"] == "2026-10-29"
    assert first["occupancy"] is not None and first["median_compset_rate"] is not None
    assert json.loads(first["kpis_extra"]) == {"brand_new_kpi": 1.5}
    assert "demand" in json.loads(first["insight_entries"])


def test_smart_insights_without_a_pms_connection() -> None:
    """Lower-tier hotels (361466) return the PMS KPIs as null; the record stays valid."""
    payload = fixture("smart_insights.json")
    for insight in payload["insights"]:
        for key in ("occupancy", "room_nights", "adr"):
            insight["kpis"][key] = None
    records = build_smart_insight_records(
        payload, hotel_id="361466", as_of_date="2026-10-29", rate_type="lowest", ota="bookingdotcom", extracted_at=NOW
    )
    valid(records, build_smart_insights_schema())
    assert records[0]["occupancy"] is None and records[0]["own_rate"] is not None


@pytest.mark.parametrize(("name", "period"), [("monthly", "2025/"), ("weekly", "2026/4")])
def test_ranking_summary_records(name: str, period: str) -> None:
    records = build_ranking_summary_records(
        fixture(f"rankings_aggregated_{name}.json"), hotel=hotel_context(), hotel_id=HOTEL, compset_id=1, extracted_at=NOW
    )
    valid(records, build_ranking_summary_schema())
    subject = [r for r in records if r["is_subject_hotel"]]
    assert subject and subject[0]["hotel_name"] == "Hilton Garden Inn Boston-Burlington"
    assert all(r["granularity"] == name and r["period"].startswith(period[:4]) for r in records)
    assert all(r["available_hotels"] is not None for r in records)


def test_latest_weekly_ranking_matches_the_page_cards() -> None:
    records = build_ranking_summary_records(
        fixture("rankings_aggregated_weekly.json"), hotel=hotel_context(), hotel_id=HOTEL, compset_id=1, extracted_at=NOW
    )
    latest = {r["ota"]: (r["ranking"], r["review_score"]) for r in records if r["period"] == "2026/44"}
    assert latest == {"bookingdotcom": (2, 7.7), "expedia": (4, 8), "tripadvisor": (3, 4.1)}


def test_ranking_daily_records_are_one_per_stay_date_and_hotel() -> None:
    records = build_ranking_daily_records(
        fixture("rankings_daily_bookingdotcom.json"),
        hotel=hotel_context(),
        hotel_id=HOTEL,
        compset_id=1,
        ota="bookingdotcom",
        as_of_date="2026-10-29",
        extracted_at=NOW,
    )
    valid(records, build_ranking_daily_schema())
    keys = {(r["stay_date"], r["hotelinfo_id"]) for r in records}
    assert len(keys) == len(records)
    tonight = next(r for r in records if r["stay_date"] == "2026-10-29" and r["is_subject_hotel"])
    assert (tonight["ranking"], tonight["price_value"], tonight["available_hotels"]) == (1, 179, 8)
    assert any(r["message"] == "ranking.not_in_search_results" for r in records)


@pytest.mark.parametrize("kind", ["base_rates", "discounts", "patterns", "cancellation"])
def test_rate_strategy_records(kind: str) -> None:
    entry = fixture("ratestrategy.json")["rate_strategies"][1]
    records = build_rate_strategy_records(
        entry, kind=kind, hotel=hotel_context(), hotel_id=HOTEL, compset_id=1, week="2026-10-19", extracted_at=NOW
    )
    valid(records, build_rate_strategy_schema(kind))
    assert all(r["snapshot_week"] == "2026-10-19" and r["hotel_name"] for r in records)
    if kind in ("discounts", "patterns"):
        assert all(r["rs_type"] and r["rs_subtype"] for r in records)


def test_unknown_rate_strategy_kind() -> None:
    with pytest.raises(ValueError, match="kind"):
        build_rate_strategy_records({}, kind="nope", hotel=hotel_context(), hotel_id=HOTEL, compset_id=1, week="x", extracted_at=NOW)


# --- weeks ---


def test_snapshot_week() -> None:
    run = date(2026, 10, 29)  # a Thursday
    assert snapshot_week({"id": "0", "extract_date": "1970-01-01"}, run_date=run) == "2026-10-26"
    assert snapshot_week({"id": "20745", "extract_date": "2026-10-19"}, run_date=run) == "2026-10-19"


def test_week_offsets() -> None:
    run = date(2026, 10, 29)
    first = week_offsets_to_fetch(run_date=run, bookmark=None, backfill_weeks=52)
    assert first[0] == -1 and first[-1] == -52 and len(first) == 52
    assert week_offsets_to_fetch(run_date=run, bookmark="2026-10-05", backfill_weeks=52) == [-1, -2, -3]
    assert week_offsets_to_fetch(run_date=run, bookmark="2026-10-26", backfill_weeks=52) == [-1]
    assert len(week_offsets_to_fetch(run_date=run, bookmark="2023-01-02", backfill_weeks=52)) == 52


# --- stream behaviour (fake browser) ---


class FakeTarget:
    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self.batches = batches
        self.calls: list[list[dict[str, Any]]] = []

    def evaluate(self, _script: str, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.calls.append(requests)
        return self.batches.pop(0)


def ok(payload: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"status": 200, "url": f"{BASE}/x", "contentType": "application/json", "text": json.dumps(payload)}


def stub_stream(config: dict[str, Any] | None = None) -> SimpleNamespace:
    from tap_lighthouse.streams_market import MarketApiStream

    stub = SimpleNamespace(
        name="rate-strategy-base-rates",
        base_url=BASE,
        hotel_id=HOTEL,
        logger=logging.getLogger("test"),
        lighthouse_tap=SimpleNamespace(config=config or {}),
        notices=[],
    )
    stub.notice = lambda message, **kw: stub.notices.append((message, kw))
    stub.api_pacer = lambda: Pacer(0, 0, sleep=lambda _s: None)
    stub.fetch_optional = lambda c, r: MarketApiStream.fetch_optional(stub, c, r)
    return stub


def test_refused_call_is_a_notice_not_a_failure() -> None:
    from tap_lighthouse.streams_market import MarketApiStream

    stub = stub_stream()
    target = FakeTarget([[{**ok({"detail": "forbidden"}), "status": 403}]])
    api = ApiClient(target, logger=logging.getLogger("test"), sleep=lambda _s: None)  # type: ignore[arg-type]
    payload = MarketApiStream.fetch_optional(stub, api, ranking_summary_request(BASE, HOTEL, granularity="weekly", compset_id=1))
    assert payload is None
    assert stub.notices and stub.notices[0][1]["code"] == "not_in_subscription"


def test_rate_strategy_snapshots_are_fetched_once_and_keyed_by_week() -> None:
    from tap_lighthouse.streams_market import RateStrategySnapshots

    current, last_week = fixture("ratestrategy.json")["rate_strategies"]
    older = {**last_week, "id": "20731", "extract_date": "2026-10-05"}  # Lighthouse skipped 2026-10-12
    target = FakeTarget([[ok({"rate_strategies": [current, last_week, older]})]])
    api = ApiClient(target, logger=logging.getLogger("test"), sleep=lambda _s: None)  # type: ignore[arg-type]
    cache = RateStrategySnapshots()
    stub = stub_stream({"rate_strategy_weeks_per_request": 8})
    run = date(2026, 10, 29)

    cache.ensure(stub, api, 1, [-1, -2, -3], run)
    cache.ensure(stub, api, 1, [-1, -2], run)  # a second stream: nothing new to fetch

    assert len(target.calls) == 1
    assert sorted(cache.by_week) == ["2026-10-05", "2026-10-19", "2026-10-26"]
    assert cache.by_week["2026-10-26"] == current


def test_rate_strategy_backfill_is_batched() -> None:
    from tap_lighthouse.streams_market import RateStrategySnapshots

    current = fixture("ratestrategy.json")["rate_strategies"][0]
    target = FakeTarget([[ok({"rate_strategies": [current]})] for _ in range(7)])
    api = ApiClient(target, logger=logging.getLogger("test"), sleep=lambda _s: None)  # type: ignore[arg-type]
    cache = RateStrategySnapshots()
    offsets = week_offsets_to_fetch(run_date=date(2026, 10, 29), bookmark=None, backfill_weeks=52)
    cache.ensure(stub_stream({"rate_strategy_weeks_per_request": 8}), api, 1, offsets, date(2026, 10, 29))
    assert len(target.calls) == 7  # 52 weeks, 8 per call
    first_url = target.calls[0][0]["url"]
    assert "weeks%5B%5D=-1&" in first_url and "weeks%5B%5D=-8" in first_url
