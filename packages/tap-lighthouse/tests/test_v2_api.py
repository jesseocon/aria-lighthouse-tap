"""v2 API streams: request shapes match captured page calls; responses map to records."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from singer_playwright.errors import ReAuthRequiredError

from tap_lighthouse.api_client import ApiClient, ApiRequest, LighthouseApiError, Pacer, camel_to_snake
from tap_lighthouse.lighthouse_api import (
    build_parity_v2_records,
    build_rates_v2_records,
    calendar_view_range,
    demands_request,
    events_request,
    hotels_request,
    occupancies_request,
    parities_request,
    parse_hotel_context,
    rates_request,
    stay_date_context,
)
from tap_lighthouse.spider_api import (
    SUMMARY_QUERY_KEYS,
    build_strategy_records,
    graphql_data,
    spider_hotel_id_from_url,
    strategy_request,
    summary_requests,
)
from tap_lighthouse.v2_schemas import (
    build_parity_list_v2_schema,
    build_rates_v2_schema,
    build_strategy_snapshot_v2_schema,
)

FIXTURES = Path(__file__).parent / "fixtures" / "api"
BASE = "https://app.mylighthouse.com"
HOTEL = "202158"


def fixture(name: str) -> Any:  # noqa: ANN401
    return json.loads((FIXTURES / name).read_text())


def hotel_context():  # noqa: ANN201
    return parse_hotel_context(fixture("hotels.json"))


# --- request shapes (copied from captured page requests) ---


def test_rates_request_matches_page() -> None:
    req = rates_request(
        BASE, HOTEL, ota="bookingdotcom", rate_type_key="lowest_flex",
        start_date="2026-09-28", end_date="2026-11-01", los=1, persons=2,
    )
    assert req.url == (
        "https://app.mylighthouse.com/apigateway/v1/app/rates/?ota=bookingdotcom&los=1&mealtype=0&persons=2"
        "&roomtype=all&membershiptype=0&compset_ids=1&platform=-1&meta=nested&bar=false&flexible=true"
        "&rate_type=0&from_date_range_start=2026-09-28&from_date_range_end=2026-11-01&hotel_id=202158"
    )
    assert req.method == "GET"
    assert req.headers["x-requested-with"] == "XMLHttpRequest"


def test_parities_request_matches_page() -> None:
    req = parities_request(BASE, HOTEL, start_date="2026-10-09", end_date="2026-10-31", los=1, persons=2)
    assert req.url == (
        "https://app.mylighthouse.com/apigateway/v1/app/parities/?hotel_id=202158&from_date_range_start=2026-10-09"
        "&from_date_range_end=2026-10-31&mealtype=0&los=1&persons=2&pos=&roomtype=all&membershiptype=0"
        "&platform=-1&meta=nested&base_membershiptype=0&bar=false&flexible=false&rate_type=0"
    )


def test_context_requests_match_page() -> None:
    kw = {"start_date": "2026-09-28", "end_date": "2026-11-01", "compare_date": "2026-10-08"}
    assert events_request(BASE, HOTEL, **kw).url == (
        "https://app.mylighthouse.com/apigateway/v1/app/events/accepted/?from_date_range_start=2026-09-28"
        "&from_date_range_end=2026-11-01&hotel_id=202158&change_dates%5B%5D=2026-10-08&subscription_id=202158"
    )
    assert demands_request(BASE, HOTEL, **kw).url.endswith(
        "demands/?from_date_range_start=2026-09-28&from_date_range_end=2026-11-01"
        "&change_dates%5B%5D=2026-10-08&subscription_id=202158"
    )
    assert occupancies_request(BASE, HOTEL, **kw).url.endswith(
        "occupancies/?subscription_id=202158&from_date_range_start=2026-09-28"
        "&from_date_range_end=2026-11-01&compare_extract_date=2026-10-08"
    )
    assert hotels_request(BASE, HOTEL).url == "https://app.mylighthouse.com/api/v3/hotels/?id=202158"


def test_calendar_view_range_is_whole_weeks() -> None:
    assert calendar_view_range("2026-10") == ("2026-09-28", "2026-11-01")
    assert calendar_view_range("2026-11") == ("2026-10-26", "2026-12-06")


def test_summary_requests_match_page_variables() -> None:
    reqs = summary_requests(
        BASE, "9203", as_of_date="2026-10-09", pickup_from="2026-10-02",
        start_date="2026-10-09", end_date="2027-10-08", currency="USD",
    )
    assert [r.label.split(":")[1] for r in reqs] == list(SUMMARY_QUERY_KEYS)
    main = json.loads(reqs[1].body or "")
    assert list(main) == ["query", "variables"]
    assert main["variables"] == {
        "hotelId": "9203",
        "filters": {"dateRange": {"start": "2026-10-09", "end": "2027-10-08"}, "pickupFrom": "2026-10-02", "asof": "2026-10-09"},
        "dateRange": {"start": "2026-10-09", "end": "2027-10-08"},
        "currency": "USD",
        "currencyVariant": "today",
        "queryKey": "main",
    }
    assert main["query"].lstrip().startswith("query GetLhDayByDayCommon(")
    assert reqs[0].url == "https://app.mylighthouse.com/apigateway/v1/proxy/spider/graphql"
    assert reqs[0].headers == {
        "content-type": "application/json",
        "x-oi-resource-id": "SP9203",
        "x-oi-resource-type": "subscription",
    }


def test_strategy_request_variables() -> None:
    req = strategy_request(
        BASE, "9203", as_of_date="2026-10-09", variance_as_of_date="2026-10-02",
        start_date="2026-10-09", end_date="2027-10-08", time_zone="America/New_York", currency="USD",
    )
    assert json.loads(req.body or "")["variables"] == {
        "hotelId": "9203",
        "asofDate": "2026-10-09",
        "varianceAsofDate": "2026-10-02",
        "dateRange": {"start": "2026-10-09", "end": "2027-10-08"},
        "timeZone": "America/New_York",
        "currency": "USD",
    }


def test_spider_hotel_id_from_frame_url() -> None:
    assert spider_hotel_id_from_url("https://spider.kriyarevgen.com/day-by-day/9203/strategy?x=1") == "9203"
    with pytest.raises(LighthouseApiError):
        spider_hotel_id_from_url("https://spider.kriyarevgen.com/login")


def test_camel_to_snake() -> None:
    assert camel_to_snake("r28RoomsAverage") == "r28_rooms_average"
    assert camel_to_snake("netStlyDowRoomsWithoutGroup") == "net_stly_dow_rooms_without_group"


# --- mapping ---


def test_hotel_context() -> None:
    hotel = hotel_context()
    assert hotel.subject_hotelinfo_id == 28650
    assert hotel.spider_id == "9203"
    assert hotel.compset_hotels(1) == (28650, 263238, 38486, 185158, 57477, 521053)
    assert hotel.compset_names == {"1": "App Primary", "-1": "RMS"}
    assert hotel.name(28646) == "DoubleTree by Hilton Hotel Boston - Bedford Glen"


def test_strategy_records_merge_variants() -> None:
    records = build_strategy_records(
        as_of_date="2026-10-09",
        pickup_from="2026-10-02",
        hotel_id=HOTEL,
        spider_hotel_id="9203",
        hotel_name="Hilton Garden Inn Boston-Burlington",
        currency="USD",
        summaries_by_key=fixture("strategy_summaries.json"),
        strategy_data=fixture("strategy_rates.json")["data"],
        extracted_at="2026-10-09T12:00:00-04:00",
    )
    assert [r["stay_date"] for r in records] == ["2026-10-17", "2026-10-20"]
    rec = records[0]
    assert rec["total_rooms"] == 147
    assert rec["asof_total_rooms"] == 131
    assert rec["stly_dow_rooms"] == 108
    assert rec["spider_forecast_rooms"] == 181
    assert rec["budget_rooms"] == pytest.approx(160.225802)
    assert rec["bar_based_rooms"] == 92
    assert rec["groups"][0]["name"] == "Green Lake Crew"
    oct20 = records[1]
    assert oct20["subject_rate"] == 349
    assert oct20["comp_set_rate_average"] == pytest.approx(332.75)
    names = {c["vendor_id"]: c["name"] for c in oct20["competitor_rates"]}
    assert names["185158"] == "Crowne Plaza Boston - Woburn by IHG"
    assert len(oct20["competitor_rates"]) == 5
    jsonschema.validate(rec, build_strategy_snapshot_v2_schema())


def test_rates_records_join_hover_context() -> None:
    hotel = hotel_context()
    context = stay_date_context(
        occupancies=fixture("occupancies.json"),
        demands=fixture("demands.json"),
        events=fixture("events.json"),
        subject_hotelinfo_id=hotel.subject_hotelinfo_id,
    )
    records = build_rates_v2_records(
        fixture("rates_bookingdotcom_lowest_flex.json"),
        month="2026-10",
        hotel=hotel,
        hotel_id=HOTEL,
        channel_key="booking_com",
        channel="Booking.com",
        ota="bookingdotcom",
        rate_type_key="lowest_flex",
        rate_type="Lowest flex",
        los=1,
        persons=2,
        compset_id=1,
        context_by_date=context,
        base_url=BASE,
        run_id="run-1",
        run_timestamp="2026-10-09T12:00:00-04:00",
    )
    assert {r["stay_date"] for r in records} == {"2026-10-01", "2026-10-17"}
    oct17 = [r for r in records if r["stay_date"] == "2026-10-17"]
    assert [r["hotelinfo_id"] for r in oct17] == [28650, 263238, 38486, 185158, 57477, 521053]
    subject = oct17[0]
    assert subject["is_subject"] is True
    assert subject["hotel_name"] == "Hilton Garden Inn Boston-Burlington"
    assert subject["my_otb_capacity"] == 181
    assert subject["market_demand"] is not None
    assert any(e["name"] == "Head of the Charles Regatta" for e in subject["events"])
    assert "hotelId=28650" in subject["redirect_url"]
    assert len({r["record_hash"] for r in records}) == len(records)
    schema = build_rates_v2_schema()
    for record in records:
        jsonschema.validate(record, schema)


def test_parity_records() -> None:
    records = build_parity_v2_records(
        fixture("parities.json"),
        month="2026-10",
        hotel=hotel_context(),
        hotel_id=HOTEL,
        los=1,
        persons=2,
        run_id="run-1",
        run_timestamp="2026-10-09T12:00:00-04:00",
    )
    assert records
    base = [r for r in records if r["is_baserate"]]
    assert base and all(r["parity_status"] == "base" for r in base)
    assert {r["parity_status"] for r in records} <= {"base", "loss", "meet", "win", None}
    assert records[0]["num_shops_major"] == 92
    assert len({r["record_hash"] for r in records}) == len(records)
    schema = build_parity_list_v2_schema()
    for record in records:
        jsonschema.validate(record, schema)


def test_graphql_errors_raise() -> None:
    from tap_lighthouse.api_client import ApiResponse

    req = ApiRequest(url="u", label="op")
    with pytest.raises(LighthouseApiError, match="GraphQL errors"):
        graphql_data(ApiResponse(req, 200, "u", "application/json", '{"errors":[{"message":"x"}]}'))
    with pytest.raises(LighthouseApiError, match="no data"):
        graphql_data(ApiResponse(req, 200, "u", "application/json", '{"data":null}'))


# --- client behaviour ---


class FakeTarget:
    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self.batches = batches
        self.calls: list[list[dict[str, Any]]] = []

    def evaluate(self, _script: str, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.calls.append(requests)
        return self.batches.pop(0)


def ok(text: str = "{}") -> dict[str, Any]:
    return {"status": 200, "url": "https://app.mylighthouse.com/x", "contentType": "application/json", "text": text}


def client(target: FakeTarget, sleeps: list[float]) -> ApiClient:
    return ApiClient(target, logger=logging.getLogger("test"), sleep=sleeps.append)  # type: ignore[arg-type]


def test_client_retries_only_failed_requests() -> None:
    target = FakeTarget([[ok('{"a":1}'), {**ok(), "status": 503}], [ok('{"b":2}')]])
    sleeps: list[float] = []
    responses = client(target, sleeps).fetch_all([ApiRequest("u1", label="a"), ApiRequest("u2", label="b")])
    assert [r.json() for r in responses] == [{"a": 1}, {"b": 2}]
    assert sleeps == [30.0]
    assert [r["url"] for r in target.calls[1]] == ["u2"]


def test_client_gives_up_after_retries() -> None:
    target = FakeTarget([[{**ok(), "status": 429}]] * 3)
    sleeps: list[float] = []
    with pytest.raises(LighthouseApiError, match="still failing"):
        client(target, sleeps).fetch_all([ApiRequest("u", label="a")])
    assert sleeps == [30.0, 120.0]


@pytest.mark.parametrize(
    "item",
    [
        {"status": 401},
        {"status": 403},
        {"url": "https://app.mylighthouse.com/login?next=/x"},
        {"contentType": "text/html; charset=utf-8", "text": "<html>"},
    ],
)
def test_client_requires_reauth(item: dict[str, Any]) -> None:
    target = FakeTarget([[{**ok(), **item}]])
    with pytest.raises(ReAuthRequiredError):
        client(target, []).fetch_all([ApiRequest("u", label="a")])


def test_client_non_retryable_error() -> None:
    target = FakeTarget([[{**ok("nope"), "status": 404}]])
    with pytest.raises(LighthouseApiError, match="404"):
        client(target, []).fetch_all([ApiRequest("u", label="a")])


def test_pacer_skips_first_pause() -> None:
    sleeps: list[float] = []
    pacer = Pacer(4, 9, sleep=sleeps.append, uniform=lambda a, b: (a + b) / 2)
    assert pacer.pause() == 0
    assert pacer.pause() == 6.5
    assert sleeps == [6.5]
