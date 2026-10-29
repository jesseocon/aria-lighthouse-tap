"""Lighthouse market-context REST requests and record mapping.

Events, holidays, demand, Smart Insights, OTA rankings and rate strategy. Parameter
names and order copy the requests the Events, Ranking and Strategy pages send
(workshop run 20261029-220956-9401d156; specs in ``briefs/``).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from tap_lighthouse.lighthouse_api import HotelContext, _rest, _url
from tap_lighthouse.api_client import ApiRequest

APP_PRIMARY_COMPSET = "App Primary"
RANKING_OTAS = ("bookingdotcom", "expedia")
RANKING_GRANULARITIES = ("weekly", "monthly")
# The current rate-strategy snapshot carries this placeholder instead of its week.
PLACEHOLDER_DATE = "1970-01-01"
# Demand rows outside Lighthouse's forward horizon carry value 0 with this message.
DEMAND_OUT_OF_RANGE = "demand.outside_allowed_date_range"

SMART_INSIGHT_KPIS = (
    "adr",
    "adr_stly",
    "adr_last_year_final",
    "adr_pickup_vs_yesterday",
    "adr_stly_pickup_vs_yesterday",
    "occupancy",
    "occupancy_stly",
    "occupancy_last_year_final",
    "occupancy_pickup_vs_yesterday",
    "occupancy_pickup_vs_3_days_ago",
    "occupancy_pickup_vs_7_days_ago",
    "occupancy_stly_pickup_vs_yesterday",
    "occupancy_stly_pickup_vs_3_days_ago",
    "occupancy_stly_pickup_vs_7_days_ago",
    "room_nights",
    "room_nights_stly",
    "room_nights_last_year_final",
    "room_nights_rooms_left_to_sell",
    "room_nights_pickup_vs_yesterday",
    "room_nights_pickup_vs_3_days_ago",
    "room_nights_pickup_vs_7_days_ago",
    "room_nights_stly_pickup_vs_yesterday",
    "room_nights_stly_pickup_vs_3_days_ago",
    "room_nights_stly_pickup_vs_7_days_ago",
    "own_rate",
    "own_rate_pickup_vs_yesterday",
    "own_rate_pickup_vs_3_days_ago",
    "own_rate_pickup_vs_7_days_ago",
    "median_compset_rate",
    "median_compset_rate_pickup_vs_yesterday",
    "median_compset_rate_pickup_vs_3_days_ago",
    "median_compset_rate_pickup_vs_7_days_ago",
    "demand",
    "demand_pickup_vs_yesterday",
    "demand_pickup_vs_3_days_ago",
    "demand_pickup_vs_7_days_ago",
    "rgi",
)


def _json(value: Any) -> str | None:  # noqa: ANN401
    return json.dumps(value, sort_keys=True, default=str) if value not in (None, {}, []) else None


def _int(value: Any) -> int | None:  # noqa: ANN401
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def app_primary_compset(hotel: HotelContext) -> int:
    """The "App Primary" comp set id (1 for every hotel seen so far)."""
    for compset_id, name in hotel.compset_names.items():
        if name.strip().lower() == APP_PRIMARY_COMPSET.lower() and compset_id.lstrip("-").isdigit():
            return int(compset_id)
    return 1


def _hotel_fields(hotel: HotelContext, hotelinfo_id: int | None) -> dict[str, Any]:
    return {
        "hotelinfo_id": hotelinfo_id,
        "hotel_name": hotel.name(hotelinfo_id) if hotelinfo_id is not None else None,
        "is_subject_hotel": hotelinfo_id == hotel.subject_hotelinfo_id if hotelinfo_id is not None else None,
    }


# --- requests ---------------------------------------------------------------


def market_events_request(base_url: str, hotel_id: str, *, start_date: str, end_date: str) -> ApiRequest:
    params = [("hotel_id", hotel_id), ("from_date_range_start", start_date), ("from_date_range_end", end_date)]
    return _rest(_url(base_url, "/apigateway/v1/app/events/", params), "events")


def holidays_request(base_url: str, hotel_id: str, *, start_date: str, end_date: str) -> ApiRequest:
    params = [("from_date_range_start", start_date), ("from_date_range_end", end_date), ("hotel_id", hotel_id)]
    return _rest(_url(base_url, "/apigateway/v1/app/holidays/", params), "holidays")


def demand_snapshot_request(base_url: str, hotel_id: str, *, start_date: str, end_date: str) -> ApiRequest:
    params = [("subscription_id", hotel_id), ("from_date_range_start", start_date), ("from_date_range_end", end_date)]
    return _rest(_url(base_url, "/apigateway/v1/app/demand/ari/demands/", params), "demand")


def smart_insights_request(
    base_url: str, hotel_id: str, *, as_of_date: str, rate_type: str, ota: str, language: str = "en"
) -> ApiRequest:
    params = [
        ("subscription_id", hotel_id),
        ("extract_date", as_of_date),
        ("from_date_start", as_of_date),
        ("rate_type", rate_type),
        ("ota", ota),
        ("language", language),
    ]
    return _rest(_url(base_url, "/apigateway/v1/app/smartinsights/insights/", params), "smart-insights")


def ranking_summary_request(base_url: str, hotel_id: str, *, granularity: str, compset_id: int, los: int = 1) -> ApiRequest:
    params = [("hotel_id", hotel_id), ("los", los), ("granularity", granularity), ("compset_ids", compset_id)]
    return _rest(_url(base_url, "/apigateway/v1/app/rankings/aggregated/", params), f"rankings-aggregated:{granularity}")


def ranking_daily_request(base_url: str, hotel_id: str, *, ota: str, compset_id: int, los: int = 1) -> ApiRequest:
    params = [
        ("ota", ota),
        ("hotel_id", hotel_id),
        ("los", los),
        ("data", "ranking"),
        ("compset_ids", compset_id),
        ("meta", "nested"),
    ]
    return _rest(_url(base_url, "/apigateway/v1/app/rankings/", params), f"rankings:{ota}")


def rate_strategy_request(base_url: str, hotel_id: str, *, compset_id: int, week_offsets: list[int]) -> ApiRequest:
    params: list[tuple[str, Any]] = [("hotel_id", hotel_id), ("compset_ids", compset_id)]
    params += [("weeks[]", offset) for offset in week_offsets]
    label = f"ratestrategy:{week_offsets[0]}..{week_offsets[-1]}" if week_offsets else "ratestrategy:current"
    return _rest(_url(base_url, "/apigateway/v1/app/ratestrategy/", params), label)


# --- weeks ------------------------------------------------------------------


def week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_offsets_to_fetch(*, run_date: date, bookmark: str | None, backfill_weeks: int) -> list[int]:
    """Negative week offsets to request, newest first.

    No bookmark: -1 back to -backfill_weeks. With one: -1 back to the bookmark's week
    (re-reading the bookmark week and last week, which Lighthouse may still revise),
    never further back than the backfill limit.
    """
    if backfill_weeks < 1:
        return [-1]
    if not bookmark:
        return list(range(-1, -backfill_weeks - 1, -1))
    this_monday = week_monday(run_date)
    bookmark_monday = week_monday(date.fromisoformat(bookmark[:10]))
    back = max(1, (this_monday - bookmark_monday).days // 7)
    return list(range(-1, -min(back, backfill_weeks) - 1, -1))


def snapshot_week(entry: dict[str, Any], *, run_date: date) -> str:
    """Monday of the week a rate-strategy snapshot describes."""
    extract = str(entry.get("extract_date") or "")[:10]
    if not extract or extract == PLACEHOLDER_DATE or str(entry.get("id")) == "0":
        return week_monday(run_date).isoformat()
    return week_monday(date.fromisoformat(extract)).isoformat()


# --- records ----------------------------------------------------------------


def build_event_records(payload: dict[str, Any], *, hotel_id: str, extracted_at: str) -> list[dict[str, Any]]:
    out = []
    for event in payload.get("events") or []:
        out.append(
            {
                "hotel_id": hotel_id,
                "event_id": str(event.get("id")),
                "event_hotel": _int(event.get("hotel")),
                "name": event.get("name"),
                "category": event.get("category"),
                "location": event.get("location"),
                "description": event.get("description"),
                "url": event.get("url"),
                "start_date": event.get("start_date"),
                "end_date": event.get("end_date"),
                "days": [str(d) for d in event.get("days") or []],
                "periods": [str(p) for p in event.get("periods") or []],
                "labels": [str(label) for label in event.get("labels") or []],
                "visitors": _int(event.get("visitors")),
                "exhibitors": _int(event.get("exhibitors")),
                "importance": _int(event.get("importance")),
                "influence_radius": event.get("influence_radius"),
                "lat": event.get("lat"),
                "lon": event.get("lon"),
                "are_exact_coordinates": event.get("are_exact_coordinates"),
                "status": event.get("status"),
                "is_cancelled": event.get("is_cancelled"),
                "is_private": event.get("is_private"),
                "is_unconfirmed": event.get("is_unconfirmed"),
                "is_new_event": event.get("is_new_event"),
                "created_timestamp": event.get("created_timestamp"),
                "last_update_timestamp": event.get("last_update_timestamp"),
                "max_distance": _int((payload.get("meta") or {}).get("max_distance")),
                "extracted_at": extracted_at,
            }
        )
    return out


def build_holiday_records(payload: dict[str, Any], *, hotel_id: str, extracted_at: str) -> list[dict[str, Any]]:
    return [
        {
            "hotel_id": hotel_id,
            "holiday_id": str(holiday.get("id")),
            "name": holiday.get("name"),
            "start_date": holiday.get("start_date"),
            "end_date": holiday.get("end_date"),
            "days": [str(d) for d in holiday.get("days") or []],
            "countries": [str(c) for c in holiday.get("countries") or []],
            "subscriptions": [i for i in (_int(s) for s in holiday.get("subscriptions") or []) if i is not None],
            "created_timestamp": holiday.get("created_timestamp"),
            "last_update_timestamp": holiday.get("last_update_timestamp"),
            "extracted_at": extracted_at,
        }
        for holiday in payload.get("holidays") or []
    ]


def build_demand_records(
    payload: dict[str, Any], *, hotel_id: str, as_of_date: str, extracted_at: str
) -> list[dict[str, Any]]:
    """Today's demand index per stay date; days outside Lighthouse's horizon are dropped."""
    out = []
    for row in payload.get("demands") or []:
        if row.get("message") == DEMAND_OUT_OF_RANGE:
            continue
        out.append(
            {
                "hotel_id": hotel_id,
                "as_of_date": as_of_date,
                "stay_date": row.get("day"),
                "demand_index": row.get("value"),
                "message": row.get("message") or None,
                "extracted_at": extracted_at,
            }
        )
    return out


def build_smart_insight_records(
    payload: dict[str, Any], *, hotel_id: str, as_of_date: str, rate_type: str, ota: str, extracted_at: str
) -> list[dict[str, Any]]:
    out = []
    for insight in payload.get("insights") or []:
        kpis = dict(insight.get("kpis") or {})
        known = {name: kpis.pop(name, None) for name in SMART_INSIGHT_KPIS}
        message = kpis.pop("message", None)
        out.append(
            {
                "hotel_id": hotel_id,
                "as_of_date": as_of_date,
                "stay_date": insight.get("stay_date"),
                "insight_id": insight.get("id"),
                "stay_date_relevance": insight.get("stay_date_relevance"),
                "stay_date_priority": insight.get("stay_date_priority"),
                "connected_dates": [str(d) for d in insight.get("connected_dates") or []],
                "rate_type": rate_type,
                "ota": ota,
                **known,
                "kpi_message": message,
                "kpis_extra": _json(kpis),
                "insight_entries": _json({k: v for k, v in (insight.get("insight_entries") or {}).items() if v}),
                "recommendation_entries": _json(
                    {k: v for k, v in (insight.get("recommendation_entries") or {}).items() if v}
                ),
                "extracted_at": extracted_at,
            }
        )
    return out


def _period_start(row: dict[str, Any]) -> str | None:
    value = str(row.get("extract_datetime") or "")[:10]
    return value or None


def build_ranking_summary_records(
    payload: dict[str, Any], *, hotel: HotelContext, hotel_id: str, compset_id: int, extracted_at: str
) -> list[dict[str, Any]]:
    out = []
    for row in payload.get("rankingsummaries") or []:
        granularity = row.get("granularity")
        hotelinfo_id = _int(row.get("hotelinfo"))
        out.append(
            {
                "hotel_id": hotel_id,
                "compset_id": compset_id,
                **_hotel_fields(hotel, hotelinfo_id),
                "ota": row.get("ota"),
                "granularity": granularity,
                "period": row.get("week") if granularity == "weekly" else row.get("month"),
                "period_start": _period_start(row),
                "ranking": _int(row.get("ranking")),
                "available_hotels": _int(row.get("available_hotels")),
                "review_score": row.get("review_score"),
                "reviews": _int(row.get("reviews")),
                "message": row.get("message") or None,
                "summary_id": row.get("id"),
                "extracted_at": extracted_at,
            }
        )
    return out


def build_ranking_daily_records(
    payload: dict[str, Any],
    *,
    hotel: HotelContext,
    hotel_id: str,
    compset_id: int,
    ota: str,
    as_of_date: str,
    extracted_at: str,
) -> list[dict[str, Any]]:
    out = []
    for period in payload.get("periods") or []:
        stay_date = period.get("from_date") or period.get("day")
        for hotelinfo, cells in (period.get("rankings") or {}).items():
            for cell in cells or []:
                hotelinfo_id = _int(cell.get("hotelinfo")) or _int(hotelinfo)
                out.append(
                    {
                        "hotel_id": hotel_id,
                        "compset_id": compset_id,
                        "as_of_date": as_of_date,
                        "stay_date": stay_date,
                        "leadtime": _int(period.get("leadtime")),
                        "los": _int(period.get("los")),
                        "ota": cell.get("ota") or ota,
                        **_hotel_fields(hotel, hotelinfo_id),
                        "ranking": _int(cell.get("ranking")),
                        "available_hotels": _int(cell.get("available_hotels")),
                        "review_score": cell.get("review_score"),
                        "reviews": _int(cell.get("reviews")),
                        "price_value": cell.get("price_value"),
                        "currency": cell.get("currency"),
                        "message": cell.get("message") or None,
                        "shopped_at": cell.get("extract_datetime"),
                        "cell_id": cell.get("id"),
                        "extracted_at": extracted_at,
                    }
                )
    return out


RATE_STRATEGY_KINDS = ("base_rates", "discounts", "patterns", "cancellation")


def _subtype_labels(entry: dict[str, Any]) -> dict[str, dict[str, str | None]]:
    """rssubtype id -> its name, label and type name."""
    type_names = {str(t.get("id")): t.get("name") for t in entry.get("rstypes") or []}
    return {
        str(s.get("id")): {
            "rs_type": type_names.get(str(s.get("rstype"))),
            "rs_subtype": s.get("name"),
            "rs_subtype_label": s.get("label"),
        }
        for s in entry.get("rssubtypes") or []
    }


def build_rate_strategy_records(
    entry: dict[str, Any],
    *,
    kind: str,
    hotel: HotelContext,
    hotel_id: str,
    compset_id: int,
    week: str,
    extracted_at: str,
) -> list[dict[str, Any]]:
    """Rows of one record kind from one weekly rate-strategy snapshot."""
    common = {"hotel_id": hotel_id, "compset_id": compset_id, "snapshot_week": week, "extracted_at": extracted_at}
    labels = _subtype_labels(entry)
    out: list[dict[str, Any]] = []
    if kind == "base_rates":
        for row in entry.get("rsbaserates") or []:
            out.append(
                {
                    **common,
                    "base_rate_id": row.get("id"),
                    **_hotel_fields(hotel, _int(row.get("hotelinfo"))),
                    "room_type": row.get("roomtype"),
                    "room_name": row.get("roomname"),
                    "pos": row.get("pos"),
                    "meal_type": _int(row.get("mealtype")),
                    "is_cancellable": row.get("is_cancellable"),
                    "is_base": row.get("is_base"),
                    "is_bar": row.get("is_bar"),
                    "rate": row.get("rate"),
                    "currency": row.get("currency"),
                    "message": row.get("message") or None,
                }
            )
    elif kind == "discounts":
        for row in entry.get("rsstrategies") or []:
            out.append(
                {
                    **common,
                    "strategy_id": row.get("id"),
                    **_hotel_fields(hotel, _int(row.get("hotelinfo"))),
                    **labels.get(str(row.get("rssubtype")), {"rs_type": None, "rs_subtype": None, "rs_subtype_label": None}),
                    "value": row.get("value"),
                    "is_absolute": row.get("is_absolute"),
                    "frequency_weekday": _int(row.get("frequency_weekday")),
                    "frequency_weekend": _int(row.get("frequency_weekend")),
                    "discounted_price": row.get("discounted_price"),
                    "base_rate_ref": row.get("rsbaserate"),
                    "message": row.get("message") or None,
                }
            )
    elif kind == "patterns":
        for row in entry.get("rspatterns") or []:
            out.append(
                {
                    **common,
                    "pattern_id": row.get("id"),
                    **_hotel_fields(hotel, _int(row.get("hotelinfo"))),
                    **labels.get(str(row.get("rssubtype")), {"rs_type": None, "rs_subtype": None, "rs_subtype_label": None}),
                    "rate": row.get("rate"),
                    "base_rate_ref": row.get("rsbaserate"),
                    "message": row.get("message") or None,
                }
            )
    elif kind == "cancellation":
        for row in entry.get("rscancellationpolicies") or []:
            subtype = labels.get(str(row.get("rssubtype")), {})
            out.append(
                {
                    **common,
                    "policy_id": row.get("id"),
                    **_hotel_fields(hotel, _int(row.get("hotelinfo"))),
                    "rs_subtype": subtype.get("rs_subtype"),
                    "days_before_arrival": _int(row.get("days")),
                    "cutoff_time": row.get("time"),
                    "frequency_weekday": _int(row.get("frequency_weekday")),
                    "frequency_weekend": _int(row.get("frequency_weekend")),
                    "base_rate_ref": row.get("rsbaserate"),
                    "message": row.get("message") or None,
                }
            )
    else:
        msg = f"Unknown rate strategy kind: {kind}"
        raise ValueError(msg)
    return out
