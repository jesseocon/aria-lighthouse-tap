"""API-based (v2) Lighthouse streams.

Each stream loads its page once (session check, real browser context), then
calls the same JSON endpoints the page uses, via in-page ``fetch``.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from singer_sdk.helpers._state import get_state_if_exists

from tap_lighthouse.api_client import ApiClient, Pacer
from tap_lighthouse.client import LighthouseStream
from tap_lighthouse.dates import add_days_iso, build_snapshot_window, compare_iso_dates, iter_iso_dates, today_iso
from tap_lighthouse.incremental import resolve_snapshot_as_of_dates
from tap_lighthouse.lighthouse_api import (
    build_parity_v2_records,
    build_rates_v2_records,
    calendar_view_range,
    demands_request,
    events_request,
    hotels_request,
    month_bounds,
    occupancies_request,
    parities_request,
    parse_hotel_context,
    rates_request,
    stay_date_context,
)
from tap_lighthouse.parity_export import new_run_metadata
from tap_lighthouse.parity_months import resolve_parity_months
from tap_lighthouse.parity_navigation import navigate_to_parity_list
from tap_lighthouse.progress import progress
from tap_lighthouse.rates_navigation import CHANNELS, navigate_to_rates, resolve_rate_types
from tap_lighthouse.rates_refresh import config_flag
from tap_lighthouse.spider_api import (
    SUMMARY_QUERY_KEYS,
    build_strategy_records,
    graphql_data,
    hotel_request,
    spider_hotel_id_from_url,
    strategy_request,
    summary_requests,
)
from tap_lighthouse.v2_schemas import (
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


class LighthouseApiStream(LighthouseStream):
    """Shared API client, pacing, and hotel context for v2 streams."""

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


class StrategySnapshotV2Stream(LighthouseApiStream):
    """Strategy page data from Spider GraphQL; incremental on as_of_date."""

    name = "strategy-snapshot-v2"
    primary_keys = ("as_of_date", "stay_date")
    replication_key = "as_of_date"
    schema = build_strategy_snapshot_v2_schema()

    def resolve_as_of_dates(self) -> list[str]:
        config = self.lighthouse_tap.config
        configured_end = config.get("end_date")
        if config.get("start_date") and configured_end:
            range_start, range_end = str(config["start_date"]), str(configured_end)
            if compare_iso_dates(range_start, range_end) > 0:
                msg = f"start_date ({range_start}) must be on or before end_date ({range_end})"
                raise ValueError(msg)
            dates = iter_iso_dates(range_start, range_end)
        else:
            bookmark = get_state_if_exists(self.tap_state, self.name, key="replication_key_value")
            dates = resolve_snapshot_as_of_dates(
                bookmark=str(bookmark) if bookmark else None,
                start_date=str(config.get("start_date") or "2025-01-01"),
                lookback_days=int(config.get("lookback_days", 7)),
                upper_bound=str(configured_end) if configured_end else today_iso(),
            )
        cap = int(config.get("strategy_v2_max_as_of_dates", 0) or 0)
        if cap > 0 and len(dates) > cap:
            self.logger.info("strategy-snapshot-v2: capping %s as-of dates to %s this run", len(dates), cap)
            dates = dates[:cap]
        return dates

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
        occupancies, demands, events = (
            r.json()
            for r in client.fetch_all(
                [
                    occupancies_request(
                        self.base_url, self.hotel_id, start_date=range_start, end_date=range_end, compare_date=compare_date
                    ),
                    demands_request(
                        self.base_url, self.hotel_id, start_date=range_start, end_date=range_end, compare_date=compare_date
                    ),
                    events_request(
                        self.base_url, self.hotel_id, start_date=range_start, end_date=range_end, compare_date=compare_date
                    ),
                ]
            )
        )
        context_by_date = stay_date_context(
            occupancies=occupancies,
            demands=demands,
            events=events,
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
