"""Market-context API streams: events, holidays, demand, Smart Insights, OTA rankings, rate strategy.

Each stream opens the page that makes these calls (session check, real browser
context), then calls the same JSON endpoints via in-page ``fetch``. A call the
hotel's subscription refuses leaves that stream empty with a notice; it does not
fail the run. Specs: ``briefs/*-page-notes.md``.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from singer_sdk.helpers._state import get_state_if_exists

from tap_lighthouse.dates import add_days_iso, today_iso
from tap_lighthouse.market_api import (
    RANKING_GRANULARITIES,
    RANKING_OTAS,
    RATE_STRATEGY_KINDS,
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
    week_monday,
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
from tap_lighthouse.progress import progress
from tap_lighthouse.streams_v2 import LighthouseApiStream

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable

    from playwright.sync_api import Page
    from singer_sdk.helpers.types import Context

    from tap_lighthouse.api_client import ApiClient, ApiRequest
    from tap_lighthouse.lighthouse_api import HotelContext


def _now() -> str:
    return datetime.now().astimezone().isoformat()


class MarketApiStream(LighthouseApiStream):
    """Opens a Lighthouse app page, then reads its JSON endpoints."""

    page_path = "/hotel/{hotel_id}/events"

    def open_page(self, page: Page) -> None:
        self.polite_sleep()
        url = f"{self.base_url}{self.page_path.format(hotel_id=self.hotel_id)}"
        page.goto(url, wait_until="domcontentloaded")

    def fetch_optional(self, client: ApiClient, request: ApiRequest) -> Any | None:  # noqa: ANN401
        """The payload, or None (with a notice) when Lighthouse refuses this call for the hotel."""
        response = client.fetch_all([replace(request, optional=True)])[0]
        if response.ok:
            return response.json()
        self.logger.warning(
            "Lighthouse %s returned %s for hotel %s; %s loads nothing for it",
            request.label,
            response.status,
            self.hotel_id,
            self.name,
        )
        self.notice(
            f"Lighthouse refused {request.label} for hotel {self.hotel_id} (status {response.status}); "
            f"{self.name} is empty for this hotel",
            code="not_in_subscription",
        )
        return None


class EventsStream(MarketApiStream):
    """Local events around the hotel, 12 months back through 12 months ahead; upsert on event_id."""

    name = "events"
    primary_keys = ("hotel_id", "event_id")
    replication_key = None
    schema = build_events_schema()

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        today = today_iso()
        start = add_days_iso(today, -int(config.get("events_days_back", 365)))
        end = add_days_iso(today, int(config.get("events_days_forward", 365)))
        self.open_page(page)
        client = self.api_client(page)
        with progress(self.logger, self.name, 1, 1, start=start, end=end) as fields:
            payload = self.fetch_optional(
                client, market_events_request(self.base_url, self.hotel_id, start_date=start, end_date=end)
            )
            records = build_event_records(payload or {}, hotel_id=self.hotel_id, extracted_at=_now())
            fields["rows"] = len(records)
            yield from records


class HolidaysStream(MarketApiStream):
    """Public holidays for the hotel's market, 12 months back through 12 months ahead."""

    name = "holidays"
    primary_keys = ("hotel_id", "holiday_id")
    replication_key = None
    schema = build_holidays_schema()

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        today = today_iso()
        start = add_days_iso(today, -int(config.get("events_days_back", 365)))
        end = add_days_iso(today, int(config.get("events_days_forward", 365)))
        self.open_page(page)
        client = self.api_client(page)
        with progress(self.logger, self.name, 1, 1, start=start, end=end) as fields:
            payload = self.fetch_optional(
                client, holidays_request(self.base_url, self.hotel_id, start_date=start, end_date=end)
            )
            records = build_holiday_records(payload or {}, hotel_id=self.hotel_id, extracted_at=_now())
            fields["rows"] = len(records)
            yield from records


class DemandStream(MarketApiStream):
    """Today's market demand index per stay date (about 60 days ahead). Daily snapshot: no history."""

    name = "demand"
    primary_keys = ("hotel_id", "as_of_date", "stay_date")
    replication_key = "as_of_date"
    schema = build_demand_schema()

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        as_of_date = today_iso()
        end = add_days_iso(as_of_date, int(self.lighthouse_tap.config.get("demand_days_forward", 90)))
        self.open_page(page)
        client = self.api_client(page)
        with progress(self.logger, self.name, 1, 1, as_of=as_of_date) as fields:
            payload = self.fetch_optional(
                client, demand_snapshot_request(self.base_url, self.hotel_id, start_date=as_of_date, end_date=end)
            )
            records = build_demand_records(
                payload or {}, hotel_id=self.hotel_id, as_of_date=as_of_date, extracted_at=_now()
            )
            fields["rows"] = len(records)
            yield from records


class SmartInsightsStream(MarketApiStream):
    """Smart Insights KPIs per stay date for the next 91 days. Daily snapshot: no history.

    Occupancy, room nights and ADR come from the hotel's PMS connection and are null
    for hotels without one; rate and demand KPIs are always filled.
    """

    name = "smart-insights"
    primary_keys = ("hotel_id", "as_of_date", "stay_date", "rate_type", "ota")
    replication_key = "as_of_date"
    schema = build_smart_insights_schema()

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        as_of_date = today_iso()
        rate_type = str(config.get("smart_insights_rate_type", "lowest"))
        ota = str(config.get("smart_insights_ota", "bookingdotcom"))
        self.open_page(page)
        client = self.api_client(page)
        with progress(self.logger, self.name, 1, 1, as_of=as_of_date, ota=ota) as fields:
            payload = self.fetch_optional(
                client,
                smart_insights_request(self.base_url, self.hotel_id, as_of_date=as_of_date, rate_type=rate_type, ota=ota),
            )
            records = build_smart_insight_records(
                payload or {},
                hotel_id=self.hotel_id,
                as_of_date=as_of_date,
                rate_type=rate_type,
                ota=ota,
                extracted_at=_now(),
            )
            fields["rows"] = len(records)
            yield from records


class RankingStream(MarketApiStream):
    page_path = "/hotel/{hotel_id}/ranking"

    def ranking_setup(self, page: Page) -> tuple[ApiClient, HotelContext, int]:
        self.open_page(page)
        client = self.api_client(page)
        hotel = self.fetch_hotel_context(client)
        return client, hotel, app_primary_compset(hotel)


class OtaRankingSummaryStream(RankingStream):
    """Weekly and monthly OTA ranking and review score, subject and comp set; upsert."""

    name = "ota-ranking-summary"
    primary_keys = ("hotel_id", "compset_id", "hotelinfo_id", "ota", "granularity", "period")
    replication_key = None
    schema = build_ranking_summary_schema()

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        client, hotel, compset_id = self.ranking_setup(page)
        pacer = self.api_pacer()
        for index, granularity in enumerate(RANKING_GRANULARITIES, start=1):
            with progress(self.logger, self.name, index, len(RANKING_GRANULARITIES), granularity=granularity) as fields:
                pacer.pause()
                payload = self.fetch_optional(
                    client,
                    ranking_summary_request(self.base_url, self.hotel_id, granularity=granularity, compset_id=compset_id),
                )
                if payload is None:
                    return
                records = build_ranking_summary_records(
                    payload, hotel=hotel, hotel_id=self.hotel_id, compset_id=compset_id, extracted_at=_now()
                )
                fields["rows"] = len(records)
                yield from records


class OtaRankingDailyStream(RankingStream):
    """OTA search rank per stay date for the comp set (Booking.com, Expedia). Daily snapshot."""

    name = "ota-ranking-daily"
    primary_keys = ("hotel_id", "compset_id", "as_of_date", "stay_date", "ota", "hotelinfo_id")
    replication_key = "as_of_date"
    schema = build_ranking_daily_schema()

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        raw = self.lighthouse_tap.config.get("ranking_otas") or RANKING_OTAS
        otas = [o.strip() for o in (raw.split(",") if isinstance(raw, str) else raw) if o.strip()]
        as_of_date = today_iso()
        client, hotel, compset_id = self.ranking_setup(page)
        pacer = self.api_pacer()
        for index, ota in enumerate(otas, start=1):
            with progress(self.logger, self.name, index, len(otas), as_of=as_of_date, ota=ota) as fields:
                pacer.pause()
                payload = self.fetch_optional(
                    client, ranking_daily_request(self.base_url, self.hotel_id, ota=ota, compset_id=compset_id)
                )
                records = build_ranking_daily_records(
                    payload or {},
                    hotel=hotel,
                    hotel_id=self.hotel_id,
                    compset_id=compset_id,
                    ota=ota,
                    as_of_date=as_of_date,
                    extracted_at=_now(),
                )
                fields["rows"] = len(records)
                yield from records


class RateStrategySnapshots:
    """Weekly rate-strategy snapshots, fetched once per run and shared by the four streams.

    Snapshots are keyed by the Monday of the week they describe (the current one by the
    run week, since Lighthouse dates it 1970-01-01). Each stream asks for the week
    offsets its own bookmark needs; offsets already requested are not requested again.
    """

    def __init__(self) -> None:
        self.by_week: dict[str, dict[str, Any]] = {}
        self.requested: set[int] = set()
        self.refused = False

    def ensure(
        self, stream: RateStrategyStream, client: ApiClient, compset_id: int, offsets: list[int], run_date: date
    ) -> None:
        missing = [offset for offset in offsets if offset not in self.requested]
        if self.refused or not missing:
            return
        per_request = max(1, int(stream.lighthouse_tap.config.get("rate_strategy_weeks_per_request", 8)))
        batches = [missing[i : i + per_request] for i in range(0, len(missing), per_request)]
        pacer = stream.api_pacer()
        for index, batch in enumerate(batches, start=1):
            with progress(stream.logger, "rate-strategy", index, len(batches), weeks=f"{batch[0]}..{batch[-1]}") as fields:
                pacer.pause()
                payload = stream.fetch_optional(
                    client, rate_strategy_request(stream.base_url, stream.hotel_id, compset_id=compset_id, week_offsets=batch)
                )
                if payload is None:
                    self.refused = True
                    return
                self.requested.update(batch)
                entries = payload.get("rate_strategies") or []
                for entry in entries:
                    self.by_week[snapshot_week(entry, run_date=run_date)] = entry
                fields["snapshots"] = len(entries)


class RateStrategyStream(MarketApiStream):
    """One record kind from the weekly rate-strategy snapshots; backfills 52 weeks on first run."""

    page_path = "/hotel/{hotel_id}/strategy"
    replication_key = "snapshot_week"
    kind = "base_rates"

    def snapshots(self) -> RateStrategySnapshots:
        tap = self.lighthouse_tap
        cache = getattr(tap, "_rate_strategy_snapshots", None)
        if cache is None:
            cache = RateStrategySnapshots()
            tap._rate_strategy_snapshots = cache  # noqa: SLF001 - one cache per tap run
        return cache

    @override
    def extract_lighthouse_records(self, page: Page, context: Context | None) -> Iterable[dict]:
        config = self.lighthouse_tap.config
        run_date = date.today()
        bookmark = get_state_if_exists(self.tap_state, self.name, key="replication_key_value")
        offsets = week_offsets_to_fetch(
            run_date=run_date,
            bookmark=str(bookmark) if bookmark else None,
            backfill_weeks=int(config.get("rate_strategy_backfill_weeks", 52)),
        )
        oldest_week = (week_monday(run_date) + timedelta(weeks=min(offsets))).isoformat()
        cache = self.snapshots()
        self.open_page(page)
        client = self.api_client(page)
        hotel = self.fetch_hotel_context(client)
        compset_id = app_primary_compset(hotel)
        cache.ensure(self, client, compset_id, offsets, run_date)
        extracted_at = _now()
        # Oldest week first and the current week last, so the bookmark only moves forward.
        for week in sorted(w for w in cache.by_week if w >= oldest_week):
            yield from build_rate_strategy_records(
                cache.by_week[week],
                kind=self.kind,
                hotel=hotel,
                hotel_id=self.hotel_id,
                compset_id=compset_id,
                week=week,
                extracted_at=extracted_at,
            )


class RateStrategyBaseRatesStream(RateStrategyStream):
    name = "rate-strategy-base-rates"
    kind = "base_rates"
    primary_keys = ("hotel_id", "compset_id", "snapshot_week", "base_rate_id")
    schema = build_rate_strategy_schema("base_rates")


class RateStrategyDiscountsStream(RateStrategyStream):
    name = "rate-strategy-discounts"
    kind = "discounts"
    primary_keys = ("hotel_id", "compset_id", "snapshot_week", "strategy_id")
    schema = build_rate_strategy_schema("discounts")


class RateStrategyPatternsStream(RateStrategyStream):
    name = "rate-strategy-patterns"
    kind = "patterns"
    primary_keys = ("hotel_id", "compset_id", "snapshot_week", "pattern_id")
    schema = build_rate_strategy_schema("patterns")


class RateStrategyCancellationStream(RateStrategyStream):
    name = "rate-strategy-cancellation"
    kind = "cancellation"
    primary_keys = ("hotel_id", "compset_id", "snapshot_week", "policy_id")
    schema = build_rate_strategy_schema("cancellation")


MARKET_STREAMS = (
    EventsStream,
    HolidaysStream,
    DemandStream,
    SmartInsightsStream,
    OtaRankingSummaryStream,
    OtaRankingDailyStream,
    RateStrategyBaseRatesStream,
    RateStrategyDiscountsStream,
    RateStrategyPatternsStream,
    RateStrategyCancellationStream,
)
assert tuple(cls.kind for cls in MARKET_STREAMS if issubclass(cls, RateStrategyStream)) == RATE_STRATEGY_KINDS
