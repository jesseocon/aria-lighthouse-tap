"""Lighthouse REST requests and record mapping for rates-v2 and parity-list-v2.

Parameter names and order copy the requests the Rates and Parity pages send.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from tap_lighthouse.api_client import APP_REST_HEADERS, ApiRequest
from tap_lighthouse.parity_months import parse_month

RATE_TYPE_API_PARAMS: dict[str, dict[str, str]] = {
    "best_flex": {"bar": "true", "flexible": "true", "rate_type": "0"},
    "lowest_flex": {"bar": "false", "flexible": "true", "rate_type": "0"},
    "lowest": {"bar": "false", "flexible": "false", "rate_type": "0"},
    "third_party": {"bar": "false", "flexible": "false", "rate_type": "1"},
}

# Inferred from captures: base (subject brand.com), loss, meet, win.
PARITY_ISSUE_TYPES = {0: "base", 3: "loss", 4: "meet", 5: "win"}

SOLD_OUT_MESSAGE = "rates.soldout"

ITEM_FIELDS = (
    "value",
    "shop_value",
    "currency",
    "shop_currency",
    "message",
    "room_name",
    "room_type",
    "cema_category",
    "rate_name",
    "rate_code",
    "best_flex",
    "cancellable",
    "cancellation",
    "mealtype_included",
    "membershiptype",
    "max_persons",
    "vat",
    "vat_incl",
    "city_tax",
    "city_tax_incl",
    "other_taxes",
    "other_taxes_incl",
    "is_out_of_sync",
    "is_wholesale_rate",
    "is_baserate",
    "source_id",
    "extract_datetime",
    "platform",
    "period",
)
PARITY_ITEM_FIELDS = (
    *ITEM_FIELDS,
    "channel",
    "unmapped_channel",
    "pos",
    "difference_with_baserate",
    "position_to_baserate",
    "issue_type",
)


def _url(base_url: str, path: str, params: list[tuple[str, Any]]) -> str:
    return f"{base_url.rstrip('/')}{path}?{urlencode([(k, str(v)) for k, v in params])}"


def _rest(url: str, label: str) -> ApiRequest:
    return ApiRequest(url=url, headers=dict(APP_REST_HEADERS), label=label)


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = parse_month(month)
    return date(year, mon, 1), date(year, mon, calendar.monthrange(year, mon)[1])


def calendar_view_range(month: str) -> tuple[str, str]:
    """Monday before the 1st through Sunday after month end, as the Rates calendar requests."""
    first, last = month_bounds(month)
    start = first - timedelta(days=first.weekday())
    end = last + timedelta(days=6 - last.weekday())
    return start.isoformat(), end.isoformat()


# Feature a subscription needs before the app calls each rates enrichment endpoint.
# The app skips the demand call for hotels without subscription.demand; so do we.
ENRICHMENT_FEATURES = {
    "occupancies": "pms.otb.view",
    "demands": "subscription.demand",
    "events": "app.events",
}


def featurescontexts_request(base_url: str, hotelinfo_id: int) -> ApiRequest:
    """Features each subscription of this hotel is entitled to (the app's capability check)."""
    return _rest(f"{base_url.rstrip('/')}/apigateway/v1/app/hotelinfos/{hotelinfo_id}/featurescontexts/", "featurescontexts")


def subscription_features(payload: dict[str, Any], subscription_id: str) -> frozenset[str] | None:
    """available_features for one subscription, or None when it is not listed."""
    for context in payload.get("featurescontexts") or []:
        if str(context.get("subscription")) == str(subscription_id):
            return frozenset(context.get("available_features") or [])
    return None


def hotels_request(base_url: str, hotel_id: str) -> ApiRequest:
    return _rest(_url(base_url, "/api/v3/hotels/", [("id", hotel_id)]), "hotels")


def rates_request(
    base_url: str,
    hotel_id: str,
    *,
    ota: str,
    rate_type_key: str,
    start_date: str,
    end_date: str,
    los: int,
    persons: int,
    compset_id: int = 1,
) -> ApiRequest:
    rt = RATE_TYPE_API_PARAMS[rate_type_key]
    params = [
        ("ota", ota),
        ("los", los),
        ("mealtype", 0),
        ("persons", persons),
        ("roomtype", "all"),
        ("membershiptype", 0),
        ("compset_ids", compset_id),
        ("platform", -1),
        ("meta", "nested"),
        ("bar", rt["bar"]),
        ("flexible", rt["flexible"]),
        ("rate_type", rt["rate_type"]),
        ("from_date_range_start", start_date),
        ("from_date_range_end", end_date),
        ("hotel_id", hotel_id),
    ]
    return _rest(_url(base_url, "/apigateway/v1/app/rates/", params), f"rates:{ota}:{rate_type_key}:{start_date}")


def parities_request(
    base_url: str, hotel_id: str, *, start_date: str, end_date: str, los: int, persons: int
) -> ApiRequest:
    params = [
        ("hotel_id", hotel_id),
        ("from_date_range_start", start_date),
        ("from_date_range_end", end_date),
        ("mealtype", 0),
        ("los", los),
        ("persons", persons),
        ("pos", ""),
        ("roomtype", "all"),
        ("membershiptype", 0),
        ("platform", -1),
        ("meta", "nested"),
        ("base_membershiptype", 0),
        ("bar", "false"),
        ("flexible", "false"),
        ("rate_type", 0),
    ]
    return _rest(_url(base_url, "/apigateway/v1/app/parities/", params), f"parities:{start_date}")


def occupancies_request(base_url: str, hotel_id: str, *, start_date: str, end_date: str, compare_date: str) -> ApiRequest:
    params = [
        ("subscription_id", hotel_id),
        ("from_date_range_start", start_date),
        ("from_date_range_end", end_date),
        ("compare_extract_date", compare_date),
    ]
    return _rest(_url(base_url, "/apigateway/v1/app/revenueinsight/occupancies/", params), "occupancies")


def demands_request(base_url: str, hotel_id: str, *, start_date: str, end_date: str, compare_date: str) -> ApiRequest:
    params = [
        ("from_date_range_start", start_date),
        ("from_date_range_end", end_date),
        ("change_dates[]", compare_date),
        ("subscription_id", hotel_id),
    ]
    return _rest(_url(base_url, "/apigateway/v1/app/demand/ari/demands/", params), "demands")


def events_request(base_url: str, hotel_id: str, *, start_date: str, end_date: str, compare_date: str) -> ApiRequest:
    params = [
        ("from_date_range_start", start_date),
        ("from_date_range_end", end_date),
        ("hotel_id", hotel_id),
        ("change_dates[]", compare_date),
        ("subscription_id", hotel_id),
    ]
    return _rest(_url(base_url, "/apigateway/v1/app/events/accepted/", params), "events")


@dataclass(frozen=True)
class HotelInfo:
    id: int
    name: str | None
    brand_code: str | None
    hotel_group: str | None


@dataclass(frozen=True)
class HotelContext:
    subject_hotelinfo_id: int
    spider_id: str | None
    hotelinfos: dict[int, HotelInfo]
    compsets: dict[str, tuple[int, ...]] = field(default_factory=dict)
    compset_names: dict[str, str] = field(default_factory=dict)

    def name(self, hotelinfo_id: int) -> str | None:
        info = self.hotelinfos.get(hotelinfo_id)
        return info.name if info else None

    def compset_hotels(self, compset_id: int) -> tuple[int, ...]:
        """Subject first, then the comp set's competitors in Lighthouse order."""
        competitors = self.compsets.get(str(compset_id), ())
        return (self.subject_hotelinfo_id, *(c for c in competitors if c != self.subject_hotelinfo_id))


def parse_hotel_context(payload: dict[str, Any]) -> HotelContext:
    hotels = payload.get("hotels") or []
    if not hotels:
        msg = "hotels response has no hotels"
        raise ValueError(msg)
    hotel = hotels[0]
    infos = {
        int(i["id"]): HotelInfo(
            id=int(i["id"]), name=i.get("name"), brand_code=i.get("brand_code"), hotel_group=i.get("hotel_group")
        )
        for i in payload.get("hotelinfos") or []
    }
    compsets: dict[str, tuple[int, ...]] = {}
    names: dict[str, str] = {}
    for compset in payload.get("compsets") or []:
        compset_id = str(compset.get("id", "")).rsplit(",", 1)[-1]
        compsets[compset_id] = tuple(int(c) for c in compset.get("competitors") or [])
        names[compset_id] = str(compset.get("name") or "")
    spider_id = hotel.get("spider_id")
    return HotelContext(
        subject_hotelinfo_id=int(hotel["hotelinfo"]),
        spider_id=str(spider_id) if spider_id else None,
        hotelinfos=infos,
        compsets=compsets,
        compset_names=names,
    )


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32]


def _item_fields(item: dict[str, Any] | None, fields: tuple[str, ...]) -> dict[str, Any]:
    item = item or {}
    out = {name: item.get(name) for name in fields}
    out["rate_id"] = item.get("id")
    out["labels"] = json.dumps(item["labels"]) if item.get("labels") else None
    out["is_sold_out"] = item.get("message") == SOLD_OUT_MESSAGE if item else None
    return out


def _change(row: dict[str, Any], key: str) -> dict[str, Any]:
    changes = row.get(key) or []
    return changes[0] if changes else {}


def stay_date_context(
    *,
    occupancies: dict[str, Any],
    demands: dict[str, Any],
    events: dict[str, Any],
    subject_hotelinfo_id: int,
) -> dict[str, dict[str, Any]]:
    """My OTB, market demand, and events per stay date (the Rates page hover content)."""
    out: dict[str, dict[str, Any]] = {}
    for row in occupancies.get("occupancies") or []:
        if row.get("hotelinfo") not in (None, subject_hotelinfo_id):
            continue
        prev = _change(row, "occupancy_changes")
        out.setdefault(str(row.get("day")), {}).update(
            {
                "my_otb_extract_date": row.get("extract_date"),
                "my_otb_rooms_booked": row.get("rooms_booked"),
                "my_otb_transient_rooms": row.get("rooms_booked_individual"),
                "my_otb_group_rooms": row.get("rooms_booked_group"),
                "my_otb_out_of_order": row.get("rooms_out_of_order"),
                "my_otb_capacity": row.get("total_capacity"),
                "my_otb_compare_extract_date": prev.get("extract_date"),
                "my_otb_compare_rooms_booked": prev.get("rooms_booked"),
                "my_otb_compare_transient_rooms": prev.get("rooms_booked_individual"),
                "my_otb_compare_group_rooms": prev.get("rooms_booked_group"),
                "my_otb_compare_out_of_order": prev.get("rooms_out_of_order"),
                "my_otb_compare_capacity": prev.get("total_capacity"),
            }
        )
    for row in demands.get("demands") or []:
        prev = _change(row, "demand_changes")
        out.setdefault(str(row.get("day")), {}).update(
            {
                "market_demand": row.get("value"),
                "market_demand_compare_extract_date": prev.get("extract_date"),
                "market_demand_compare": prev.get("value"),
            }
        )
    for event in events.get("events") or []:
        summary = {
            "name": event.get("name"),
            "category": event.get("category"),
            "start_date": event.get("start_date"),
            "end_date": event.get("end_date"),
            "visitors": event.get("visitors"),
            "is_cancelled": event.get("is_cancelled"),
        }
        for day in event.get("days") or []:
            out.setdefault(str(day), {}).setdefault("events", []).append(summary)
    return out


def redirect_url(base_url: str, hotel_id: str, *, ota: str, hotelinfo_id: int, stay_date: str, los: int, persons: int) -> str:
    params = [
        ("ota", ota),
        ("hotelId", hotelinfo_id),
        ("direct", "false"),
        ("fromDate", stay_date),
        ("los", los),
        ("persons", persons),
        ("city", "false"),
        ("subscription_id", hotel_id),
        ("pos", ""),
        ("source", "app_rates"),
    ]
    return _url(base_url, "/redirect", params)


def build_rates_v2_records(
    payload: dict[str, Any],
    *,
    month: str,
    hotel: HotelContext,
    hotel_id: str,
    channel_key: str,
    channel: str,
    ota: str,
    rate_type_key: str,
    rate_type: str,
    los: int,
    persons: int,
    compset_id: int,
    context_by_date: dict[str, dict[str, Any]],
    base_url: str,
    run_id: str,
    run_timestamp: str,
) -> list[dict[str, Any]]:
    """One record per stay date in ``month`` x comp-set hotel x rate item (or one empty row)."""
    first, last = month_bounds(month)
    hotel_ids = hotel.compset_hotels(compset_id)
    records: list[dict[str, Any]] = []
    for period in payload.get("periods") or []:
        stay_date = str(period.get("from_date") or period.get("day") or "")
        if not stay_date or not (first.isoformat() <= stay_date <= last.isoformat()):
            continue
        rates = period.get("rates") or {}
        context = context_by_date.get(stay_date, {})
        for hotelinfo_id in hotel_ids:
            items = rates.get(str(hotelinfo_id)) or [None]
            for position, item in enumerate(items):
                info = hotel.hotelinfos.get(hotelinfo_id)
                key = {
                    "run_id": run_id,
                    "stay_date": stay_date,
                    "ota": ota,
                    "rate_type_key": rate_type_key,
                    "los": los,
                    "persons": persons,
                    "compset_id": compset_id,
                    "hotelinfo_id": hotelinfo_id,
                    "position": position,
                }
                records.append(
                    {
                        "record_hash": _hash(key),
                        "run_id": run_id,
                        "run_timestamp": run_timestamp,
                        "hotel_id": hotel_id,
                        "month": month,
                        "stay_date": stay_date,
                        "leadtime": period.get("leadtime"),
                        "channel_key": channel_key,
                        "channel": channel,
                        "ota": ota,
                        "rate_type_key": rate_type_key,
                        "rate_type": rate_type,
                        "los": los,
                        "persons": persons,
                        "compset_id": compset_id,
                        "compset_name": hotel.compset_names.get(str(compset_id)),
                        "hotelinfo_id": hotelinfo_id,
                        "hotel_name": info.name if info else None,
                        "hotel_brand_code": info.brand_code if info else None,
                        "hotel_group": info.hotel_group if info else None,
                        "is_subject": hotelinfo_id == hotel.subject_hotelinfo_id,
                        "item_position": position,
                        "has_rate": item is not None,
                        **_item_fields(item, ITEM_FIELDS),
                        "redirect_url": redirect_url(
                            base_url,
                            hotel_id,
                            ota=ota,
                            hotelinfo_id=hotelinfo_id,
                            stay_date=stay_date,
                            los=los,
                            persons=persons,
                        ),
                        **{k: v for k, v in context.items() if k != "events"},
                        "events": context.get("events", []),
                    }
                )
    return records


def build_parity_v2_records(
    payload: dict[str, Any],
    *,
    month: str,
    hotel: HotelContext,
    hotel_id: str,
    los: int,
    persons: int,
    run_id: str,
    run_timestamp: str,
) -> list[dict[str, Any]]:
    """One record per stay date x OTA x channel offer, as shown in the Parity list."""
    meta = payload.get("meta") or {}
    first, last = month_bounds(month)
    records: list[dict[str, Any]] = []
    for period in payload.get("periods") or []:
        stay_date = str(period.get("from_date") or period.get("day") or "")
        if not stay_date or not (first.isoformat() <= stay_date <= last.isoformat()):
            continue
        for position, item in enumerate(period.get("parities") or []):
            hotelinfo_id = item.get("hotelinfo")
            key = {
                "run_id": run_id,
                "stay_date": stay_date,
                "ota": item.get("ota"),
                "channel": item.get("channel"),
                "pos": item.get("pos"),
                "position": position,
            }
            issue_type = item.get("issue_type")
            records.append(
                {
                    "record_hash": _hash(key),
                    "run_id": run_id,
                    "run_timestamp": run_timestamp,
                    "hotel_id": hotel_id,
                    "month": month,
                    "stay_date": stay_date,
                    "leadtime": period.get("leadtime"),
                    "los": los,
                    "persons": persons,
                    "hotelinfo_id": hotelinfo_id,
                    "hotel_name": hotel.name(int(hotelinfo_id)) if hotelinfo_id is not None else None,
                    "ota": item.get("ota"),
                    "item_position": position,
                    **_item_fields(item, PARITY_ITEM_FIELDS),
                    "parity_status": PARITY_ISSUE_TYPES.get(issue_type) if issue_type is not None else None,
                    "num_shops_major": meta.get("num_shops_major"),
                    "num_shops_other": meta.get("num_shops_other"),
                }
            )
    return records
