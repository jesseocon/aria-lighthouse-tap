"""API-based (v2) Lighthouse streams.

Each stream loads its page once (session check, real browser context), then
calls the same JSON endpoints the page uses, via in-page ``fetch``.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from singer_sdk.helpers._state import get_state_if_exists

from tap_lighthouse.api_client import ApiClient, LighthouseApiError, Pacer
from tap_lighthouse.client import LighthouseStream
from tap_lighthouse.dates import add_days_iso, build_snapshot_window, compare_iso_dates, iter_iso_dates, today_iso
from tap_lighthouse.incremental import resolve_snapshot_as_of_dates
from tap_lighthouse.lighthouse_api import (
    ENRICHMENT_FEATURES,
    build_parity_v2_records,
    build_rates_v2_records,
    calendar_view_range,
    demands_request,
    events_request,
    featurescontexts_request,
    hotels_request,
    month_bounds,
    occupancies_request,
    parities_request,
    parse_hotel_context,
    rates_request,
    stay_date_context,
    subscription_features,
)
from tap_lighthouse.parity_export import new_run_metadata
from tap_lighthouse.parity_months import resolve_parity_months
from tap_lighthouse.navigation import DayByDayUrlOptions, navigate_to_day_by_day
from tap_lighthouse.parity_navigation import navigate_to_parity_list
from tap_lighthouse.progress import progress
from tap_lighthouse.rates_navigation import CHANNELS, navigate_to_rates, resolve_rate_types
from tap_lighthouse.rates_refresh import config_flag
from tap_lighthouse.spider_api import (
    SUMMARY_QUERY_KEYS,
    build_length_of_stay_records,
    build_market_segment_records,
    build_room_type_records,
    build_rate_plan_records,
    build_strategy_records,
    graphql_data,
    hotel_request,
    length_of_stay_request,
    market_segments_request,
    room_types_request,
    rate_plans_request,
    spider_hotel_id_from_url,
    strategy_request,
    summary_requests,
)
from tap_lighthouse.v2_schemas import (
    build_length_of_stay_schema,
    build_market_segments_schema,
    build_room_type_schema,
    build_rate_plans_schema,
    build_parity_list_v2_schema,
    build_rates_v2_schema,
    build_strategy_snapshot_v2_schema,
)

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable

    from playwright.sync_api import Frame, Page
    from singer_sdk.helpers.types import Context

    from tap_lighthouse.lighthouse_api import HotelContext


def snapshot_as_of_dates(stream: LighthouseApiStream, *, cap_key: str) -> list[str]:
    """As-of dates for an incremental Spider snapshot, oldest first."""
    config = stream.lighthouse_tap.config
    configured_end = config.get("end_date")
    if config.get("start_date") and configured_end:
        range_start, range_end = str(config["start_date"]), str(configured_end)
        if compare_iso_dates(range_start, range_end) > 0:
            msg = f"start_date ({range_start}) must be on or before end_date ({range_end})"
            raise ValueError(msg)
        dates = iter_iso_dates(range_start, range_end)
    else:
        bookmark = get_state_if_exists(stream.tap_state, stream.name, key="replication_key_value")
        dates = resolve_snapshot_as_of_dates(
            bookmark=str(bookmark) if bookmark else None,
            start_date=str(config.get("start_date") or "2025-01-01"),
            lookback_days=int(config.get("lookback_days", 7)),
            upper_bound=str(configured_end) if configured_end else today_iso(),
        )
    cap = int(config.get(cap_key, 0) or 0)
    if cap > 0 and len(dates) > cap:
        stream.logger.info("%s: capping %s as-of dates to %s this run", stream.name, len(dates), cap)
        dates = dates[:cap]
    return dates


class LighthouseApiStream(LighthouseStream):
    """Shared API client, pacing, and hotel context for v2 streams."""

    _enrichment_notice_sent = False

    @property
    def base_url(self) -> str:
        return str(self.lighthouse_tap.config.get("base_url", "https://app.mylighthouse.com")).rstrip("/")

    def api_client(self, target: Page | Frame) -> ApiClient:
        return ApiClient(target, logger=self.logger)

    def api_pacer(self) -> Pacer:
        config = self.lighthouse_tap.config
        return Pacer(
            float(config.get("api_pause_min_seconds", 4)),
            float(config.get("api_pause_max_seconds", 9)),
        )

    def fetch_hotel_context(self, client: ApiClient) -> HotelContext:
        return parse_hotel_context(client.fetch_json(hotels_request(self.base_url, self.hotel_id)))

    def subscription_features(self, client: ApiClient, hotel: HotelContext) -> frozenset[str] | None:
        """Features this hotel's subscription has, as the app reads them. None if unreadable."""
        try:
            payload = client.fetch_json(featurescontexts_request(self.base_url, hotel.subject_hotelinfo_id))
        except LighthouseApiError as exc:
            self.logger.warning("Could not read Lighthouse features for hotel %s (%s)", self.hotel_id, exc)
            return None
        return subscription_features(payload, self.hotel_id)

    def fetch_enrichment(
        self, client: ApiClient, hotel: HotelContext, *, start_date: str, end_date: str, compare_date: str
    ) -> dict[str, dict]:
        """My OTB, demand and events for the rates hover, calling only what the hotel is entitled to.

        A call whose feature the subscription lacks is not made (the app skips it too). If the
        features cannot be read, every call is made, and a refusal leaves those columns empty.
        """
        builders = {"occupancies": occupancies_request, "demands": demands_request, "events": events_request}
        features = self.subscription_features(client, hotel)
        wanted = {
            name: replace(
                build(self.base_url, self.hotel_id, start_date=start_date, end_date=end_date, compare_date=compare_date),
                optional=True,
            )
            for name, build in builders.items()
            if features is None or ENRICHMENT_FEATURES[name] in features
        }
        skipped = [name for name in builders if name not in wanted]
        if skipped:
            self.logger.info(
                "Hotel %s has no %s; not calling %s",
                self.hotel_id,
                ", ".join(ENRICHMENT_FEATURES[name] for name in skipped),
                ", ".join(skipped),
            )
            if not self._enrichment_notice_sent:
                self._enrichment_notice_sent = True
                self.notice(
                    f"Subscription has no {', '.join(ENRICHMENT_FEATURES[name] for name in skipped)}; "
                    f"{', '.join(skipped)} columns stay empty",
                    code="not_in_subscription",
                )
        out: dict[str, dict] = {name: {} for name in builders}
        if wanted:
            for name, response in zip(wanted, client.fetch_all(list(wanted.values())), strict=True):
                if response.ok:
                    out[name] = response.json()
                else:
                    self.logger.warning(
                        "Lighthouse %s returned %s for hotel %s; leaving those columns empty",
                        name,
                        response.status,
                        self.hotel_id,
                    )
        return out


class StrategySnapshotV2Stream(LighthouseApiStream):
    """Strategy page data from Spider GraphQL; incremental on as_of_date."""

    name = "strategy-snapshot-v2"
    primary_keys = ("as_of_date", "stay_date")
    replication_key = "as_of_date"
    schema = build_strategy_snapshot_v2_schema()

    def resolve_as_of_dates(self) -> list[str]:
        return snapshot_as_of_dates(self, cap_key="strategy_v2_max_as_of_dates")

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        window_days = int(config.get("window_days", 365))
        pickup_days = int(config.get("strategy_v2_pickup_days", 7))
        as_of_dates = self.resolve_as_of_dates()
        if not as_of_dates:
            self.logger.info("No as_of_date values to sync for strategy-snapshot-v2")
            return

        landing = build_snapshot_window(as_of_dates[-1], window_days)
        frame = self.navigate_strategy_frame(
            page, start_date=landing.start_date, end_date=landing.end_date, as_of_date=landing.as_of_date
        )
        spider_id = spider_hotel_id_from_url(frame.url)
        client = self.api_client(frame)
        hotel = graphql_data(client.fetch_all([hotel_request(self.base_url, spider_id)])[0])["hotelContext"]
        currency = str((hotel.get("currency") or {}).get("code") or "USD")
        time_zone = str(hotel.get("timeZone") or "America/New_York")
        hotel_name = str(hotel.get("name") or "")
        pacer = self.api_pacer()

        for index, as_of_date in enumerate(as_of_dates, start=1):
            window = build_snapshot_window(as_of_date, window_days)
            pickup_from = add_days_iso(as_of_date, -pickup_days)
            with progress(
                self.logger, self.name, index, len(as_of_dates), as_of=as_of_date, pickup_from=pickup_from
            ) as fields:
                pacer.pause()
                requests = [
                    *summary_requests(
                        self.base_url,
                        spider_id,
                        as_of_date=as_of_date,
                        pickup_from=pickup_from,
                        start_date=window.start_date,
                        end_date=window.end_date,
                        currency=currency,
                    ),
                    strategy_request(
                        self.base_url,
                        spider_id,
                        as_of_date=as_of_date,
                        variance_as_of_date=pickup_from,
                        start_date=window.start_date,
                        end_date=window.end_date,
                        time_zone=time_zone,
                        currency=currency,
                    ),
                ]
                responses = client.fetch_all(requests)
                summaries = {
                    key: graphql_data(resp)["lhDayByDaySummaries"] or []
                    for key, resp in zip(SUMMARY_QUERY_KEYS, responses, strict=False)
                }
                records = build_strategy_records(
                    as_of_date=as_of_date,
                    pickup_from=pickup_from,
                    hotel_id=self.hotel_id,
                    spider_hotel_id=spider_id,
                    hotel_name=hotel_name,
                    currency=currency,
                    summaries_by_key=summaries,
                    strategy_data=graphql_data(responses[-1]),
                    extracted_at=datetime.now().astimezone().isoformat(),
                )
                fields["rows"] = len(records)
                yield from records


class MarketSegmentsStream(LighthouseApiStream):
    """Market-segment OTB from Spider GraphQL; incremental on as_of_date."""

    name = "market-segments"
    primary_keys = ("as_of_date", "stay_date", "market_segment")
    replication_key = "as_of_date"
    schema = build_market_segments_schema()

    def resolve_as_of_dates(self) -> list[str]:
        return snapshot_as_of_dates(self, cap_key="strategy_v2_max_as_of_dates")

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        window_days = int(config.get("window_days", 365))
        pickup_days = int(config.get("strategy_v2_pickup_days", 7))
        as_of_dates = self.resolve_as_of_dates()
        if not as_of_dates:
            self.logger.info("No as_of_date values to sync for market-segments")
            return

        landing = build_snapshot_window(as_of_dates[-1], window_days)
        self.polite_sleep()
        frame = navigate_to_day_by_day(
            page,
            self.hotel_id,
            view="market-segments",
            options=DayByDayUrlOptions(start_date=landing.start_date, end_date=landing.end_date),
        )
        spider_id = spider_hotel_id_from_url(frame.url)
        client = self.api_client(frame)
        hotel = graphql_data(client.fetch_all([hotel_request(self.base_url, spider_id)])[0])["hotelContext"]
        currency = str((hotel.get("currency") or {}).get("code") or "USD")
        hotel_name = str(hotel.get("name") or "")
        pacer = self.api_pacer()

        for index, as_of_date in enumerate(as_of_dates, start=1):
            window = build_snapshot_window(as_of_date, window_days)
            pickup_from = add_days_iso(as_of_date, -pickup_days)
            with progress(
                self.logger, self.name, index, len(as_of_dates), as_of=as_of_date, pickup_from=pickup_from
            ) as fields:
                pacer.pause()
                response = client.fetch_all(
                    [
                        market_segments_request(
                            self.base_url,
                            spider_id,
                            as_of_date=as_of_date,
                            pickup_from=pickup_from,
                            start_date=window.start_date,
                            end_date=window.end_date,
                            currency=currency,
                        )
                    ]
                )[0]
                records = build_market_segment_records(
                    as_of_date=as_of_date,
                    pickup_from=pickup_from,
                    hotel_id=self.hotel_id,
                    spider_hotel_id=spider_id,
                    hotel_name=hotel_name,
                    currency=currency,
                    segments_data=graphql_data(response),
                    extracted_at=datetime.now().astimezone().isoformat(),
                )
                fields["rows"] = len(records)
                yield from records


class RatePlansStream(LighthouseApiStream):
    """Rate-plan OTB from Spider GraphQL; incremental on as_of_date."""

    name = "rate-plans"
    primary_keys = ("as_of_date", "stay_date", "market_segment", "rate_plan")
    replication_key = "as_of_date"
    schema = build_rate_plans_schema()

    def resolve_as_of_dates(self) -> list[str]:
        return snapshot_as_of_dates(self, cap_key="strategy_v2_max_as_of_dates")

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        window_days = int(config.get("window_days", 365))
        pickup_days = int(config.get("strategy_v2_pickup_days", 7))
        as_of_dates = self.resolve_as_of_dates()
        if not as_of_dates:
            self.logger.info("No as_of_date values to sync for rate-plans")
            return

        landing = build_snapshot_window(as_of_dates[-1], window_days)
        self.polite_sleep()
        frame = navigate_to_day_by_day(
            page,
            self.hotel_id,
            view="rate-plans",
            options=DayByDayUrlOptions(start_date=landing.start_date, end_date=landing.end_date),
        )
        spider_id = spider_hotel_id_from_url(frame.url)
        client = self.api_client(frame)
        hotel = graphql_data(client.fetch_all([hotel_request(self.base_url, spider_id)])[0])["hotelContext"]
        currency = str((hotel.get("currency") or {}).get("code") or "USD")
        hotel_name = str(hotel.get("name") or "")
        pacer = self.api_pacer()

        for index, as_of_date in enumerate(as_of_dates, start=1):
            window = build_snapshot_window(as_of_date, window_days)
            pickup_from = add_days_iso(as_of_date, -pickup_days)
            with progress(
                self.logger, self.name, index, len(as_of_dates), as_of=as_of_date, pickup_from=pickup_from
            ) as fields:
                pacer.pause()
                response = client.fetch_all(
                    [
                        rate_plans_request(
                            self.base_url,
                            spider_id,
                            as_of_date=as_of_date,
                            pickup_from=pickup_from,
                            start_date=window.start_date,
                            end_date=window.end_date,
                            currency=currency,
                        )
                    ]
                )[0]
                records = build_rate_plan_records(
                    as_of_date=as_of_date,
                    pickup_from=pickup_from,
                    hotel_id=self.hotel_id,
                    spider_hotel_id=spider_id,
                    hotel_name=hotel_name,
                    currency=currency,
                    rate_plans_data=graphql_data(response),
                    extracted_at=datetime.now().astimezone().isoformat(),
                )
                fields["rows"] = len(records)
                yield from records


class LengthOfStayStream(LighthouseApiStream):
    """Length-of-stay OTB from Spider GraphQL; incremental on as_of_date."""

    name = "length-of-stay"
    primary_keys = ("as_of_date", "stay_date", "length_of_stay")
    replication_key = "as_of_date"
    schema = build_length_of_stay_schema()

    def resolve_as_of_dates(self) -> list[str]:
        return snapshot_as_of_dates(self, cap_key="strategy_v2_max_as_of_dates")

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        window_days = int(config.get("window_days", 365))
        pickup_days = int(config.get("strategy_v2_pickup_days", 7))
        as_of_dates = self.resolve_as_of_dates()
        if not as_of_dates:
            self.logger.info("No as_of_date values to sync for length-of-stay")
            return

        landing = build_snapshot_window(as_of_dates[-1], window_days)
        self.polite_sleep()
        frame = navigate_to_day_by_day(
            page,
            self.hotel_id,
            view="length-of-stay",
            options=DayByDayUrlOptions(start_date=landing.start_date, end_date=landing.end_date),
        )
        spider_id = spider_hotel_id_from_url(frame.url)
        client = self.api_client(frame)
        hotel = graphql_data(client.fetch_all([hotel_request(self.base_url, spider_id)])[0])["hotelContext"]
        currency = str((hotel.get("currency") or {}).get("code") or "USD")
        hotel_name = str(hotel.get("name") or "")
        pacer = self.api_pacer()

        for index, as_of_date in enumerate(as_of_dates, start=1):
            window = build_snapshot_window(as_of_date, window_days)
            pickup_from = add_days_iso(as_of_date, -pickup_days)
            with progress(
                self.logger, self.name, index, len(as_of_dates), as_of=as_of_date, pickup_from=pickup_from
            ) as fields:
                pacer.pause()
                response = client.fetch_all(
                    [
                        length_of_stay_request(
                            self.base_url,
                            spider_id,
                            as_of_date=as_of_date,
                            pickup_from=pickup_from,
                            start_date=window.start_date,
                            end_date=window.end_date,
                            currency=currency,
                        )
                    ]
                )[0]
                records = build_length_of_stay_records(
                    as_of_date=as_of_date,
                    pickup_from=pickup_from,
                    hotel_id=self.hotel_id,
                    spider_hotel_id=spider_id,
                    hotel_name=hotel_name,
                    currency=currency,
                    length_of_stay_data=graphql_data(response),
                    extracted_at=datetime.now().astimezone().isoformat(),
                )
                fields["rows"] = len(records)
                yield from records


class RoomTypeStream(LighthouseApiStream):
    """Room-type OTB from Spider GraphQL; incremental on as_of_date."""

    name = "room-type"
    primary_keys = ("as_of_date", "stay_date", "room_type")
    replication_key = "as_of_date"
    schema = build_room_type_schema()

    def resolve_as_of_dates(self) -> list[str]:
        return snapshot_as_of_dates(self, cap_key="strategy_v2_max_as_of_dates")

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        window_days = int(config.get("window_days", 365))
        pickup_days = int(config.get("strategy_v2_pickup_days", 7))
        as_of_dates = self.resolve_as_of_dates()
        if not as_of_dates:
            self.logger.info("No as_of_date values to sync for room-type")
            return

        landing = build_snapshot_window(as_of_dates[-1], window_days)
        self.polite_sleep()
        frame = navigate_to_day_by_day(
            page,
            self.hotel_id,
            view="room-type",
            options=DayByDayUrlOptions(start_date=landing.start_date, end_date=landing.end_date),
        )
        spider_id = spider_hotel_id_from_url(frame.url)
        client = self.api_client(frame)
        hotel = graphql_data(client.fetch_all([hotel_request(self.base_url, spider_id)])[0])["hotelContext"]
        currency = str((hotel.get("currency") or {}).get("code") or "USD")
        hotel_name = str(hotel.get("name") or "")
        pacer = self.api_pacer()

        for index, as_of_date in enumerate(as_of_dates, start=1):
            window = build_snapshot_window(as_of_date, window_days)
            pickup_from = add_days_iso(as_of_date, -pickup_days)
            with progress(
                self.logger, self.name, index, len(as_of_dates), as_of=as_of_date, pickup_from=pickup_from
            ) as fields:
                pacer.pause()
                response = client.fetch_all(
                    [
                        room_types_request(
                            self.base_url,
                            spider_id,
                            as_of_date=as_of_date,
                            pickup_from=pickup_from,
                            start_date=window.start_date,
                            end_date=window.end_date,
                            currency=currency,
                        )
                    ]
                )[0]
                records = build_room_type_records(
                    as_of_date=as_of_date,
                    pickup_from=pickup_from,
                    hotel_id=self.hotel_id,
                    spider_hotel_id=spider_id,
                    hotel_name=hotel_name,
                    currency=currency,
                    room_types_data=graphql_data(response),
                    extracted_at=datetime.now().astimezone().isoformat(),
                )
                fields["rows"] = len(records)
                yield from records


class RatesV2Stream(LighthouseApiStream):
    """Comp-set rates from the Rates API, with My OTB, demand, and events; append-only."""

    name = "rates-v2"
    primary_keys = ("record_hash",)
    replication_key = "run_timestamp"
    schema = build_rates_v2_schema()

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        los = int(config.get("parity_los", 1))
        persons = int(config.get("parity_max_persons", 2))
        compset_id = 1
        months = resolve_parity_months(forward_months=int(config.get("rates_forward_months", 1)))
        rate_types = resolve_rate_types(config.get("rates_rate_types"))
        if not months:
            return
        run_id, run_timestamp = new_run_metadata()
        compare_date = (date.today() - timedelta(days=1)).isoformat()

        refresh = config_flag(config.get("rates_v2_refresh", False), default=False)
        _first_key, _first_label, first_ota = CHANNELS[0]
        navigate_to_rates(
            page,
            self.hotel_id,
            month=months[0],
            ota_id=first_ota,
            rate_param=rate_types[0][2],
            los=los,
            max_persons=persons,
            base_url=self.base_url,
        )
        client = self.api_client(page)
        pacer = self.api_pacer()
        hotel = self.fetch_hotel_context(client)

        range_start = calendar_view_range(months[0])[0]
        range_end = calendar_view_range(months[-1])[1]
        pacer.pause()
        enrichment = self.fetch_enrichment(
            client, hotel, start_date=range_start, end_date=range_end, compare_date=compare_date
        )
        context_by_date = stay_date_context(
            occupancies=enrichment["occupancies"],
            demands=enrichment["demands"],
            events=enrichment["events"],
            subject_hotelinfo_id=hotel.subject_hotelinfo_id,
        )

        specs = [
            (month, channel, rate_type) for month in months for channel in CHANNELS for rate_type in rate_types
        ]
        self.logger.info("Starting rates-v2 run_id=%s calls=%s refresh=%s", run_id, len(specs), refresh)
        refreshed: set[tuple[str, str]] = set()
        for index, (month, (channel_key, channel, ota), (rt_key, rt_label, rt_param)) in enumerate(specs, start=1):
            with progress(self.logger, self.name, index, len(specs), month=month, channel=channel, rate_type=rt_label) as fields:
                if refresh and (month, ota) not in refreshed:
                    self._refresh(page, month=month, ota=ota, channel=channel, rate_param=rt_param, los=los, persons=persons)
                    refreshed.add((month, ota))
                pacer.pause()
                start, end = calendar_view_range(month)
                payload = client.fetch_json(
                    rates_request(
                        self.base_url,
                        self.hotel_id,
                        ota=ota,
                        rate_type_key=rt_key,
                        start_date=start,
                        end_date=end,
                        los=los,
                        persons=persons,
                        compset_id=compset_id,
                    )
                )
                records = build_rates_v2_records(
                    payload,
                    month=month,
                    hotel=hotel,
                    hotel_id=self.hotel_id,
                    channel_key=channel_key,
                    channel=channel,
                    ota=ota,
                    rate_type_key=rt_key,
                    rate_type=rt_label,
                    los=los,
                    persons=persons,
                    compset_id=compset_id,
                    context_by_date=context_by_date,
                    base_url=self.base_url,
                    run_id=run_id,
                    run_timestamp=run_timestamp,
                )
                fields["rows"] = len(records)
                yield from records

    def _refresh(self, page: Page, *, month: str, ota: str, channel: str, rate_param: str | None, los: int, persons: int) -> None:
        """Opt-in live shop through the v1 UI refresh (clicks the page's Refresh button)."""
        from tap_lighthouse.rates_refresh import (
            DEFAULT_POLL_SECONDS,
            DEFAULT_RECENT_SECONDS,
            DEFAULT_TIMEOUT_SECONDS,
            refresh_rates_page,
        )

        config = self.lighthouse_tap.config

        def reload() -> Any:  # noqa: ANN401
            return navigate_to_rates(
                page,
                self.hotel_id,
                month=month,
                ota_id=ota,
                rate_param=rate_param,
                los=los,
                max_persons=persons,
                base_url=self.base_url,
            )

        reload()
        refresh_rates_page(
            page,
            channel=channel,
            reload=reload,
            timeout_seconds=int(config.get("rates_refresh_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
            poll_seconds=float(config.get("rates_refresh_poll_seconds", DEFAULT_POLL_SECONDS)),
            recent_seconds=int(config.get("rates_refresh_recent_seconds", DEFAULT_RECENT_SECONDS)),
            logger=self.logger,
        )


class ParityListV2Stream(LighthouseApiStream):
    """Parity list from the Parities API, one record per stay date x OTA offer; append-only."""

    name = "parity-list-v2"
    primary_keys = ("record_hash",)
    replication_key = "run_timestamp"
    schema = build_parity_list_v2_schema()

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        los = int(config.get("parity_los", 1))
        persons = int(config.get("parity_max_persons", 2))
        months = resolve_parity_months(forward_months=int(config.get("parity_forward_months", 2)))
        if not months:
            return
        run_id, run_timestamp = new_run_metadata()
        navigate_to_parity_list(
            page, self.hotel_id, los=los, max_persons=persons, month=months[0], base_url=self.base_url
        )
        client = self.api_client(page)
        pacer = self.api_pacer()
        hotel = self.fetch_hotel_context(client)
        today = date.today()
        self.logger.info("Starting parity-list-v2 run_id=%s months=%s", run_id, months)

        for index, month in enumerate(months, start=1):
            with progress(self.logger, self.name, index, len(months), month=month) as fields:
                first, last = month_bounds(month)
                pacer.pause()
                payload = client.fetch_json(
                    parities_request(
                        self.base_url,
                        self.hotel_id,
                        start_date=max(first, today).isoformat(),
                        end_date=last.isoformat(),
                        los=los,
                        persons=persons,
                    )
                )
                records = build_parity_v2_records(
                    payload,
                    month=month,
                    hotel=hotel,
                    hotel_id=self.hotel_id,
                    los=los,
                    persons=persons,
                    run_id=run_id,
                    run_timestamp=run_timestamp,
                )
                fields["rows"] = len(records)
                yield from records
