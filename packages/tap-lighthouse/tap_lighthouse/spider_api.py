"""Spider (Strategy page) GraphQL requests and record mapping for strategy-snapshot-v2."""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources
from typing import Any

from tap_lighthouse.api_client import ApiRequest, ApiResponse, LighthouseApiError, camel_to_snake

GRAPHQL_PATH = "/apigateway/v1/proxy/spider/graphql"
SPIDER_ID_RE = re.compile(r"/day-by-day/(\d+)")

# Order the Strategy page issues them in; each variant fills a disjoint set of fields.
SUMMARY_QUERY_KEYS = ("group_bar", "main", "asof", "stly", "main_kriya", "budget_forecast")

SUMMARY_FIELDS = (
    "inventory",
    "totalRooms",
    "totalRevenue",
    "transientRooms",
    "transientRevenue",
    "groupOtbRooms",
    "groupOtbRevenue",
    "groupBlockRooms",
    "groupBlockRevenue",
    "outOfOrder",
    "barBasedPace",
    "barBasedRevenue",
    "barBasedRooms",
    "budgetRevenue",
    "budgetRooms",
    "financeForecastRevenue",
    "financeForecastRooms",
    "hurdle",
    "optimalBar",
    "systemRate",
    "r28RoomsAverage",
    "rmsForecastRevenue",
    "rmsForecastRooms",
    "spiderForecastRevenue",
    "spiderForecastRooms",
    "spiderForecastUnconstrainedRooms",
    "userForecastRevenue",
    "userForecastRooms",
    "stlyDowRevenue",
    "stlyDowRooms",
    "stlyDowRevenueWithoutGroup",
    "stlyDowRoomsWithoutGroup",
    "stlyDowRevenueWithGroup",
    "stlyDowRoomsWithGroup",
    "netStlyDowRevenue",
    "netStlyDowRooms",
    "netStlyDowRevenueWithoutGroup",
    "netStlyDowRoomsWithoutGroup",
    "netStlyDowRevenueWithGroup",
    "netStlyDowRoomsWithGroup",
)
ASOF_FIELDS = (
    "groupBlockRevenue",
    "groupBlockRooms",
    "groupOtbRevenue",
    "groupOtbRooms",
    "inventory",
    "outOfOrder",
    "spiderForecastRevenue",
    "spiderForecastRooms",
    "totalRevenue",
    "totalRooms",
    "transientRevenue",
    "transientRooms",
)
LAST_YEAR_FIELDS = (
    "cancelled",
    "dayUseRevenue",
    "dayUseRooms",
    "groupBlockRevenue",
    "groupBlockRooms",
    "groupOtbRevenue",
    "groupOtbRooms",
    "inventory",
    "outOfOrder",
    "totalRevenue",
    "totalRooms",
    "transientRevenue",
    "transientRooms",
)

# Observed owner of each field (365 stay dates, hotel 9203). Unlisted fields take the
# first non-zero variant value, falling back to ``main``.
FIELD_OWNER: dict[str, str] = {
    **dict.fromkeys(
        (
            "inventory",
            "totalRooms",
            "totalRevenue",
            "transientRooms",
            "transientRevenue",
            "groupOtbRooms",
            "groupOtbRevenue",
            "groupBlockRooms",
        ),
        "main",
    ),
    **{f"asof.{name}": "asof" for name in ("totalRooms", "totalRevenue", "groupBlockRooms", "groupOtbRooms")},
    **dict.fromkeys(
        (
            "stlyDowRevenue",
            "stlyDowRooms",
            "stlyDowRevenueWithoutGroup",
            "stlyDowRoomsWithoutGroup",
            "stlyDowRevenueWithGroup",
            "stlyDowRoomsWithGroup",
            "netStlyDowRevenue",
            "netStlyDowRooms",
            "netStlyDowRevenueWithoutGroup",
            "netStlyDowRoomsWithoutGroup",
            "netStlyDowRevenueWithGroup",
            "netStlyDowRoomsWithGroup",
            "lastYearDow.totalRooms",
            "lastYearDow.totalRevenue",
            "lastYearDow.groupBlockRevenue",
        ),
        "stly",
    ),
    **dict.fromkeys(
        (
            "spiderForecastRevenue",
            "spiderForecastRooms",
            "spiderForecastUnconstrainedRooms",
            "rmsForecastRevenue",
            "rmsForecastRooms",
            "optimalBar",
            "systemRate",
            "barBasedPace",
            "r28RoomsAverage",
            "hurdle",
        ),
        "main_kriya",
    ),
    "budgetRooms": "budget_forecast",
    "budgetRevenue": "budget_forecast",
    "barBasedRooms": "group_bar",
    "groups": "group_bar",
}

MERGED_FIELDS: tuple[str, ...] = (
    *SUMMARY_FIELDS,
    *(f"asof.{name}" for name in ASOF_FIELDS),
    *(f"lastYearDow.{name}" for name in LAST_YEAR_FIELDS),
    "groups",
)


def column_name(field: str) -> str:
    prefix, _, name = field.rpartition(".")
    column = camel_to_snake(name)
    if prefix == "asof":
        return f"asof_{column}"
    if prefix == "lastYearDow":
        return f"last_year_dow_{column}"
    return column


@cache
def load_document(name: str) -> str:
    return resources.files("tap_lighthouse.graphql").joinpath(f"{name}.graphql").read_text(encoding="utf-8")


def spider_hotel_id_from_url(url: str) -> str:
    match = SPIDER_ID_RE.search(url or "")
    if not match:
        msg = f"Could not find the Spider hotel id in the strategy frame URL: {url}"
        raise LighthouseApiError(msg)
    return match.group(1)


def graphql_request(base_url: str, spider_hotel_id: str, operation: str, variables: dict[str, Any], *, label: str = "") -> ApiRequest:
    body = json.dumps({"query": load_document(operation), "variables": variables}, separators=(",", ":"))
    return ApiRequest(
        url=f"{base_url.rstrip('/')}{GRAPHQL_PATH}",
        method="POST",
        headers={
            "content-type": "application/json",
            "x-oi-resource-id": f"SP{spider_hotel_id}",
            "x-oi-resource-type": "subscription",
        },
        body=body,
        label=label or operation,
    )


def hotel_request(base_url: str, spider_hotel_id: str) -> ApiRequest:
    variables = {"hotelId": spider_hotel_id, "currency": None, "dataReplatforming": None}
    return graphql_request(base_url, spider_hotel_id, "GetHotel", variables)


def summary_requests(
    base_url: str,
    spider_hotel_id: str,
    *,
    as_of_date: str,
    pickup_from: str,
    start_date: str,
    end_date: str,
    currency: str,
) -> list[ApiRequest]:
    date_range = {"start": start_date, "end": end_date}
    return [
        graphql_request(
            base_url,
            spider_hotel_id,
            "GetLhDayByDayCommon",
            {
                "hotelId": spider_hotel_id,
                "filters": {"dateRange": dict(date_range), "pickupFrom": pickup_from, "asof": as_of_date},
                "dateRange": dict(date_range),
                "currency": currency,
                "currencyVariant": "today",
                "queryKey": key,
            },
            label=f"GetLhDayByDayCommon:{key}",
        )
        for key in SUMMARY_QUERY_KEYS
    ]


def strategy_request(
    base_url: str,
    spider_hotel_id: str,
    *,
    as_of_date: str,
    variance_as_of_date: str,
    start_date: str,
    end_date: str,
    time_zone: str,
    currency: str,
) -> ApiRequest:
    variables = {
        "hotelId": spider_hotel_id,
        "asofDate": as_of_date,
        "varianceAsofDate": variance_as_of_date,
        "dateRange": {"start": start_date, "end": end_date},
        "timeZone": time_zone,
        "currency": currency,
    }
    return graphql_request(base_url, spider_hotel_id, "GetDayByDayStrategy", variables)


def graphql_data(response: ApiResponse) -> dict[str, Any]:
    payload = response.json()
    if not isinstance(payload, dict):
        msg = f"{response.request.label}: unexpected GraphQL payload"
        raise LighthouseApiError(msg)
    if payload.get("errors"):
        msg = f"{response.request.label}: GraphQL errors {json.dumps(payload['errors'])[:500]}"
        raise LighthouseApiError(msg)
    data = payload.get("data")
    if not isinstance(data, dict):
        msg = f"{response.request.label}: GraphQL response has no data"
        raise LighthouseApiError(msg)
    return data


def _flatten_summary(row: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {name: row.get(name) for name in SUMMARY_FIELDS}
    asof = row.get("asof") or {}
    flat.update({f"asof.{name}": asof.get(name) for name in ASOF_FIELDS})
    last_year = row.get("lastYearDow") or {}
    flat.update({f"lastYearDow.{name}": last_year.get(name) for name in LAST_YEAR_FIELDS})
    flat["groups"] = row.get("groups") or []
    return flat


def _is_empty(value: Any) -> bool:  # noqa: ANN401
    return value is None or value == 0 or value == []


def _pick(field: str, values: dict[str, Any]) -> Any:  # noqa: ANN401
    owner = FIELD_OWNER.get(field)
    if owner and owner in values:
        return values[owner]
    for key in SUMMARY_QUERY_KEYS:
        if key in values and not _is_empty(values[key]):
            return values[key]
    return values.get("main")


def merge_summaries(summaries_by_key: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Combine the six query-key variants into one field set per stay date."""
    by_date: dict[str, dict[str, dict[str, Any]]] = {}
    for key, rows in summaries_by_key.items():
        for row in rows:
            stay_date = str(row.get("date") or "")
            if stay_date:
                by_date.setdefault(stay_date, {})[key] = _flatten_summary(row)
    merged: dict[str, dict[str, Any]] = {}
    for stay_date in sorted(by_date):
        variants = by_date[stay_date]
        merged[stay_date] = {
            field: _pick(field, {key: flat[field] for key, flat in variants.items()}) for field in MERGED_FIELDS
        }
    return merged


def _number(value: Any) -> float | None:  # noqa: ANN401
    if value is None or value == "":
        return None
    return float(value)


def build_strategy_records(
    *,
    as_of_date: str,
    pickup_from: str,
    hotel_id: str,
    spider_hotel_id: str,
    hotel_name: str,
    currency: str,
    summaries_by_key: dict[str, list[dict[str, Any]]],
    strategy_data: dict[str, Any],
    extracted_at: str,
) -> list[dict[str, Any]]:
    rates = strategy_data.get("rates") or {}
    metadata = (rates.get("metadata") or [{}])[0] or {}
    competitor_names = {str(c.get("vendorId")): c.get("name") for c in metadata.get("competitors") or []}
    rate_by_date: dict[str, dict[str, Any]] = {}
    for period in rates.get("periods") or []:
        period_rates = period.get("rates") or []
        if period_rates:
            rate_by_date[str(period.get("date"))] = period_rates[0]
    notes_by_date = {str(s.get("date")): s.get("notes") or "" for s in strategy_data.get("userSummaries") or []}

    records: list[dict[str, Any]] = []
    for stay_date, fields in merge_summaries(summaries_by_key).items():
        rate = rate_by_date.get(stay_date) or {}
        record: dict[str, Any] = {
            "as_of_date": as_of_date,
            "stay_date": stay_date,
            "pickup_from": pickup_from,
            "hotel_id": hotel_id,
            "spider_hotel_id": spider_hotel_id,
            "hotel_name": hotel_name,
            "currency": currency,
        }
        for field, value in fields.items():
            if field == "groups":
                continue
            record[column_name(field)] = _number(value)
        record["groups"] = [
            {"name": g.get("name"), "rooms": _number(g.get("rooms")), "revenue": _number(g.get("revenue"))}
            for g in fields["groups"]
        ]
        record.update(
            {
                "rate_channel": metadata.get("channel"),
                "rate_bar": metadata.get("bar"),
                "rate_los": metadata.get("los"),
                "rate_guests": metadata.get("guests"),
                "subject_rate": _number(rate.get("rate")),
                "subject_rate_variance": _number(rate.get("rateVariance")),
                "comp_set_rate_average": _number(rate.get("competitorRateAverage")),
                "comp_set_rate_average_variance": _number(rate.get("competitorRateAverageVariance")),
                "competitor_rates": [
                    {
                        "vendor_id": str(c.get("vendorId")),
                        "name": competitor_names.get(str(c.get("vendorId"))),
                        "rate": _number(c.get("rate")),
                        "rate_variance": _number(c.get("rateVariance")),
                    }
                    for c in rate.get("competitorRates") or []
                ],
                "notes": notes_by_date.get(stay_date, ""),
                "extracted_at": extracted_at,
            }
        )
        records.append(record)
    return records
