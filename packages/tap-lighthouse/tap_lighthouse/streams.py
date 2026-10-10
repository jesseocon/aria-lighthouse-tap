"""Lighthouse Singer streams."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from singer_sdk import typing as th
from singer_sdk.helpers._state import get_state_if_exists

from tap_lighthouse.client import LighthouseStream
from tap_lighthouse.dates import build_snapshot_window, compare_iso_dates, iter_iso_dates, today_iso
from tap_lighthouse.export import enrich_snapshot_records, extract_table_records
from tap_lighthouse.incremental import resolve_snapshot_as_of_dates
from tap_lighthouse.parity_export import (
    enrich_parity_records,
    extract_parity_rows_with_hovers,
    new_run_metadata,
)
from tap_lighthouse.parity_months import resolve_parity_months
from tap_lighthouse.parity_navigation import navigate_to_parity_list
from tap_lighthouse.parity_provenance import build_sync_params, hash_sync_params
from tap_lighthouse.progress import progress
from tap_lighthouse.budget_export import (
    build_sync_params as build_budget_sync_params,
    enrich_budget_records,
    extract_budget_rows,
    hash_sync_params as hash_budget_sync_params,
    new_run_metadata as new_budget_run_metadata,
)
from tap_lighthouse.budget_months import resolve_budget_months
from tap_lighthouse.budget_navigation import navigate_to_budget
from tap_lighthouse.budget_schema import build_budget_schema
from tap_lighthouse.forecast_export import (
    build_sync_params as build_forecast_sync_params,
    enrich_forecast_records,
    extract_forecast_rows,
    hash_sync_params as hash_forecast_sync_params,
    new_run_metadata as new_forecast_run_metadata,
)
from tap_lighthouse.forecast_navigation import navigate_to_forecast, resolve_forecast_entry_id
from tap_lighthouse.forecast_schema import build_forecast_schema
from tap_lighthouse.parity_list_schema import build_parity_list_schema
from tap_lighthouse.rates_export import (
    build_rates_records,
    enrich_rates_records,
    extract_rates_rows_with_hovers,
)
from tap_lighthouse.rates_navigation import CHANNELS, navigate_to_rates, resolve_rate_types
from tap_lighthouse.rates_refresh import (
    DEFAULT_POLL_SECONDS,
    DEFAULT_RECENT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    RefreshObservation,
    config_flag,
    observe_without_click,
    read_rates_updated_label,
    refresh_rates_page,
)
from tap_lighthouse.rates_schema import build_rates_schema
from tap_lighthouse.strategy_snapshot_schema import build_strategy_snapshot_schema

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from playwright.sync_api import Page
    from singer_sdk.helpers.types import Context


STRATEGY_SNAPSHOT_SCHEMA = build_strategy_snapshot_schema()
PARITY_LIST_SCHEMA = build_parity_list_schema()
RATES_SCHEMA = build_rates_schema()
BUDGET_SCHEMA = build_budget_schema()
FORECAST_SCHEMA = build_forecast_schema()


class StrategySnapshotStream(LighthouseStream):
    """Sliding-window strategy snapshot; incremental on as_of_date."""

    name = "strategy-snapshot"
    primary_keys = ("as_of_date", "stay_date")
    replication_key = "as_of_date"
    schema = STRATEGY_SNAPSHOT_SCHEMA

    @override
    def extract_lighthouse_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        tap = self.lighthouse_tap
        window_days = int(tap.config.get("window_days", 365))
        default_start = str(tap.config.get("start_date") or "2025-01-01")
        configured_end = tap.config.get("end_date")
        upper_bound = str(configured_end) if configured_end else today_iso()
        lookback_days = int(tap.config.get("lookback_days", 7))

        prior_bookmark = get_state_if_exists(
            self.tap_state,
            self.name,
            key="replication_key_value",
        )

        if tap.config.get("start_date") and configured_end:
            range_start = str(tap.config["start_date"])
            range_end = str(configured_end)
            if compare_iso_dates(range_start, range_end) > 0:
                msg = f"start_date ({range_start}) must be on or before end_date ({range_end})"
                raise ValueError(msg)
            as_of_dates = iter_iso_dates(range_start, range_end)
        else:
            as_of_dates = resolve_snapshot_as_of_dates(
                bookmark=str(prior_bookmark) if prior_bookmark else None,
                start_date=default_start,
                lookback_days=lookback_days,
                upper_bound=upper_bound,
            )

        if not as_of_dates:
            self.logger.info("No as_of_date values to sync for strategy-snapshot")
            return

        for index, as_of_date in enumerate(as_of_dates, start=1):
            window = build_snapshot_window(as_of_date, window_days)
            with progress(
                self.logger,
                "strategy-snapshot",
                index,
                len(as_of_dates),
                as_of=window.as_of_date,
                range=f"{window.start_date}..{window.end_date}",
            ) as fields:
                frame = self.navigate_strategy_frame(
                    page,
                    start_date=window.start_date,
                    end_date=window.end_date,
                    as_of_date=window.as_of_date,
                )
                self.polite_sleep()
                rows = extract_table_records(frame, hotel_id=self.hotel_id)
                fields["rows"] = len(rows)
                yield from enrich_snapshot_records(rows, as_of_date=window.as_of_date)
                self.polite_sleep()


class ParityListStream(LighthouseStream):
    """Parity list monthly snapshots with hover detail; append-only run history."""

    name = "parity-list"
    primary_keys = ("record_hash",)
    replication_key = "run_timestamp"
    schema = PARITY_LIST_SCHEMA

    @override
    def extract_lighthouse_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        tap = self.lighthouse_tap
        los = int(tap.config.get("parity_los", 1))
        max_persons = int(tap.config.get("parity_max_persons", 2))
        forward_months = int(tap.config.get("parity_forward_months", 2))
        hover_delay_ms = int(tap.config.get("parity_hover_delay_ms", 300))
        base_url = str(tap.config.get("base_url", "https://app.mylighthouse.com"))

        months = resolve_parity_months(forward_months=forward_months)
        if not months:
            self.logger.info("No parity months to sync")
            return

        run_id, run_timestamp = new_run_metadata()
        self.logger.info(
            "Starting parity-list run_id=%s run_timestamp=%s months=%s",
            run_id,
            run_timestamp,
            months,
        )

        for index, month in enumerate(months, start=1):
            with progress(self.logger, "parity-list", index, len(months), month=month) as fields:
                url = navigate_to_parity_list(
                    page,
                    self.hotel_id,
                    los=los,
                    max_persons=max_persons,
                    month=month,
                    base_url=base_url,
                )
                self.polite_sleep()
                sync_params = build_sync_params(
                    hotel_id=self.hotel_id,
                    month=month,
                    los=los,
                    max_persons=max_persons,
                    url=url,
                    page=page,
                )
                sync_params_hash = hash_sync_params(sync_params)
                _, rows = extract_parity_rows_with_hovers(
                    page,
                    include_hovers=True,
                    hover_delay_ms=hover_delay_ms,
                )
                fields["rows"] = len(rows)
                yield from enrich_parity_records(
                    rows,
                    run_id=run_id,
                    run_timestamp=run_timestamp,
                    sync_params=sync_params,
                    sync_params_hash=sync_params_hash,
                    hotel_id=self.hotel_id,
                    month=month,
                )
                self.polite_sleep()


class RatesStream(LighthouseStream):
    """Append-only compset rate snapshots, one refresh per channel page."""

    name = "rates"
    primary_keys = ("record_hash",)
    replication_key = "run_timestamp"
    schema = RATES_SCHEMA

    @override
    def extract_lighthouse_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        tap = self.lighthouse_tap
        los = int(tap.config.get("parity_los", 1))
        max_persons = int(tap.config.get("parity_max_persons", 2))
        forward_months = int(tap.config.get("rates_forward_months", 1))
        hover_delay_ms = int(tap.config.get("parity_hover_delay_ms", 300))
        base_url = str(tap.config.get("base_url", "https://app.mylighthouse.com"))

        months = resolve_parity_months(forward_months=forward_months)
        rate_types = resolve_rate_types(tap.config.get("rates_rate_types"))
        if not months:
            self.logger.info("No rates months to sync")
            return

        run_id, run_timestamp = new_run_metadata()
        self.logger.info(
            "Starting rates run_id=%s months=%s channels=%s rate_types=%s",
            run_id,
            months,
            [label for _key, label, _ota in CHANNELS],
            [label for _key, label, _param in rate_types],
        )

        pages = [
            (month, channel_key, channel, ota_id, rate_type_key, rate_type, rate_param)
            for month in months
            for channel_key, channel, ota_id in CHANNELS
            for rate_type_key, rate_type, rate_param in rate_types
        ]
        for index, page_spec in enumerate(pages, start=1):
            month, channel_key, channel, ota_id, rate_type_key, rate_type, rate_param = page_spec
            with progress(
                self.logger,
                "rates",
                index,
                len(pages),
                month=month,
                channel=channel,
                rate_type=rate_type,
            ) as fields:
                url = navigate_to_rates(
                    page,
                    self.hotel_id,
                    month=month,
                    ota_id=ota_id,
                    rate_param=rate_param,
                    los=los,
                    max_persons=max_persons,
                    base_url=base_url,
                )
                self.polite_sleep()
                refresh = self._refresh_rates_channel(
                    page,
                    channel,
                    reload=lambda month=month, ota_id=ota_id, rate_param=rate_param: (
                        navigate_to_rates(
                            page,
                            self.hotel_id,
                            month=month,
                            ota_id=ota_id,
                            rate_param=rate_param,
                            los=los,
                            max_persons=max_persons,
                            base_url=base_url,
                        )
                    ),
                )
                table_rows = extract_rates_rows_with_hovers(
                    page,
                    hover_delay_ms=hover_delay_ms,
                )
                records = build_rates_records(
                    table_rows,
                    month=month,
                    channel=channel,
                    channel_key=channel_key,
                    rate_type=rate_type,
                    rate_type_key=rate_type_key,
                    los=str(los),
                    max_persons=str(max_persons),
                )
                sync_params = {
                    "hotel_id": self.hotel_id,
                    "month": month,
                    "channel": channel,
                    "channel_key": channel_key,
                    "rate_type": rate_type,
                    "rate_type_key": rate_type_key,
                    "ota_id": ota_id,
                    "rate_param": rate_param or "",
                    "compset_id": "1",
                    "los": los,
                    "max_persons": max_persons,
                    "device": "Desktop",
                    "room": "Any room",
                    "meal": "Any meal",
                    "url": url,
                    "refreshed_at": refresh.refreshed_at,
                    "refresh_label": refresh.refresh_label,
                    "refresh_clicked": refresh.clicked,
                }
                fields["rows"] = len(records)
                fields["refreshed_at"] = refresh.refreshed_at
                yield from enrich_rates_records(
                    records,
                    run_id=run_id,
                    run_timestamp=run_timestamp,
                    refreshed_at=refresh.refreshed_at,
                    refresh_label=refresh.refresh_label,
                    sync_params=sync_params,
                    hotel_id=self.hotel_id,
                )
                self.polite_sleep()

    def _refresh_rates_channel(
        self,
        page: Page,
        channel: str,
        *,
        reload: Callable[[], object],
    ) -> RefreshObservation:
        tap = self.lighthouse_tap
        if not config_flag(tap.config.get("rates_refresh", True)):
            return observe_without_click(read_rates_updated_label(page))
        return refresh_rates_page(
            page,
            channel=channel,
            reload=reload,
            timeout_seconds=int(
                tap.config.get("rates_refresh_timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            ),
            poll_seconds=float(
                tap.config.get("rates_refresh_poll_seconds", DEFAULT_POLL_SECONDS),
            ),
            recent_seconds=int(
                tap.config.get("rates_refresh_recent_seconds", DEFAULT_RECENT_SECONDS),
            ),
            logger=self.logger,
        )


class BudgetStream(LighthouseStream):
    """Budget monthly snapshots; append-only run history."""

    name = "budget"
    primary_keys = ("record_hash",)
    replication_key = "run_timestamp"
    schema = BUDGET_SCHEMA

    @override
    def extract_lighthouse_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        tap = self.lighthouse_tap
        variance = str(tap.config.get("budget_variance", "absolute"))
        start_month = tap.config.get("budget_start_month")
        forward_months = int(tap.config.get("budget_forward_months", 2))
        base_url = str(tap.config.get("base_url", "https://app.mylighthouse.com"))

        months = resolve_budget_months(
            start_month=str(start_month) if start_month else None,
            forward_months=forward_months,
        )
        if not months:
            self.logger.info("No budget months to sync")
            return

        run_id, run_timestamp = new_budget_run_metadata()
        self.logger.info(
            "Starting budget run_id=%s run_timestamp=%s months=%s..%s (%s month(s))",
            run_id,
            run_timestamp,
            months[0],
            months[-1],
            len(months),
        )

        for index, month in enumerate(months, start=1):
            with progress(self.logger, "budget", index, len(months), month=month) as fields:
                url = navigate_to_budget(
                    page,
                    self.hotel_id,
                    month=month,
                    variance=variance,
                    base_url=base_url,
                )
                self.polite_sleep()
                sync_params = build_budget_sync_params(
                    hotel_id=self.hotel_id,
                    month=month,
                    variance=variance,
                    url=url,
                )
                sync_params_hash = hash_budget_sync_params(sync_params)
                _, rows = extract_budget_rows(page)
                fields["rows"] = len(rows)
                yield from enrich_budget_records(
                    rows,
                    run_id=run_id,
                    run_timestamp=run_timestamp,
                    sync_params=sync_params,
                    sync_params_hash=sync_params_hash,
                    hotel_id=self.hotel_id,
                    month=month,
                )
                self.polite_sleep()


class ForecastStream(LighthouseStream):
    """Forecast monthly snapshots; append-only run history."""

    name = "forecast"
    primary_keys = ("record_hash",)
    replication_key = "run_timestamp"
    schema = FORECAST_SCHEMA

    @override
    def extract_lighthouse_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        tap = self.lighthouse_tap
        start_month = tap.config.get("forecast_start_month")
        forward_months = int(tap.config.get("forecast_forward_months", 2))
        base_url = str(tap.config.get("base_url", "https://app.mylighthouse.com"))

        months = resolve_budget_months(
            start_month=str(start_month) if start_month else None,
            forward_months=forward_months,
        )
        if not months:
            self.logger.info("No forecast months to sync")
            return

        entry_id, entry_id_source = resolve_forecast_entry_id(
            page,
            self.hotel_id,
            base_url=base_url,
        )
        self.logger.info(
            "Resolved forecast entry_id=%s (source=%s)",
            entry_id,
            entry_id_source,
        )

        run_id, run_timestamp = new_forecast_run_metadata()
        self.logger.info(
            "Starting forecast run_id=%s run_timestamp=%s months=%s..%s (%s month(s))",
            run_id,
            run_timestamp,
            months[0],
            months[-1],
            len(months),
        )

        for index, month in enumerate(months, start=1):
            with progress(self.logger, "forecast", index, len(months), month=month) as fields:
                url = navigate_to_forecast(
                    page,
                    self.hotel_id,
                    entry_id=entry_id,
                    month=month,
                    base_url=base_url,
                )
                self.polite_sleep()
                sync_params = build_forecast_sync_params(
                    hotel_id=self.hotel_id,
                    entry_id=entry_id,
                    month=month,
                    url=url,
                    entry_id_source=entry_id_source,
                )
                sync_params_hash = hash_forecast_sync_params(sync_params)
                _, rows = extract_forecast_rows(page)
                fields["rows"] = len(rows)
                yield from enrich_forecast_records(
                    rows,
                    run_id=run_id,
                    run_timestamp=run_timestamp,
                    sync_params=sync_params,
                    sync_params_hash=sync_params_hash,
                    hotel_id=self.hotel_id,
                    month=month,
                )
                self.polite_sleep()
