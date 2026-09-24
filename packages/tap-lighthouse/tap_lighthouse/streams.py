"""Lighthouse Singer streams."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from singer_sdk import typing as th
from singer_sdk.helpers._state import get_state_if_exists

from tap_lighthouse.client import LighthouseStream
from tap_lighthouse.dates import build_snapshot_window, compare_iso_dates, iter_iso_dates, today_iso
from tap_lighthouse.export import enrich_snapshot_records, extract_table_records
from tap_lighthouse.incremental import IncrementalConfig, resolve_snapshot_as_of_dates
from tap_lighthouse.parity_export import (
    enrich_parity_records,
    extract_parity_rows_with_hovers,
    new_run_metadata,
)
from tap_lighthouse.parity_months import resolve_parity_months
from tap_lighthouse.parity_navigation import navigate_to_parity_list
from tap_lighthouse.parity_provenance import build_sync_params, hash_sync_params
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
from tap_lighthouse.strategy_snapshot_schema import build_strategy_snapshot_schema

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable

    from playwright.sync_api import Page
    from singer_sdk.helpers.types import Context


STRATEGY_SNAPSHOT_SCHEMA = build_strategy_snapshot_schema()
PARITY_LIST_SCHEMA = build_parity_list_schema()
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
        bookmark = self.get_starting_replication_key_value(context)
        full_refresh = prior_bookmark is None
        state = {
            "bookmarks": {
                self.name: {
                    "replication_key": self.replication_key,
                    "replication_key_value": prior_bookmark or bookmark,
                },
            },
        }
        incremental = IncrementalConfig(
            mode="lookback",
            timeframe="days",
            timeframe_quantity=lookback_days,
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
                state=state,
                stream_name=self.name,
                full_refresh=full_refresh,
                default_start=default_start,
                incremental=incremental,
                upper_bound=upper_bound,
            )

        if not as_of_dates:
            self.logger.info("No as_of_date values to sync for strategy-snapshot")
            return

        for as_of_date in as_of_dates:
            window = build_snapshot_window(as_of_date, window_days)
            self.logger.info(
                "Exporting strategy-snapshot as_of=%s range=%s..%s",
                window.as_of_date,
                window.start_date,
                window.end_date,
            )

            frame = self.navigate_strategy_frame(
                page,
                start_date=window.start_date,
                end_date=window.end_date,
                as_of_date=window.as_of_date,
            )
            self.polite_sleep()
            rows = extract_table_records(frame, hotel_id=self.hotel_id)
            self.logger.info(
                "Extracted %s row(s) for strategy-snapshot as_of=%s",
                len(rows),
                window.as_of_date,
            )
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

        for month in months:
            self.logger.info("Exporting parity-list month=%s", month)
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
            self.logger.info("Extracted %s parity row(s) for month=%s", len(rows), month)
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
        entry_id = str(tap.config.get("budget_entry_id", "19564"))
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

        for month in months:
            self.logger.info("Exporting budget month=%s", month)
            url = navigate_to_budget(
                page,
                self.hotel_id,
                entry_id=entry_id,
                month=month,
                variance=variance,
                base_url=base_url,
            )
            self.polite_sleep()
            sync_params = build_budget_sync_params(
                hotel_id=self.hotel_id,
                entry_id=entry_id,
                month=month,
                variance=variance,
                url=url,
            )
            sync_params_hash = hash_budget_sync_params(sync_params)
            _, rows = extract_budget_rows(page)
            self.logger.info("Extracted %s budget row(s) for month=%s", len(rows), month)
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
        configured_entry_id = tap.config.get("forecast_entry_id")
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
            configured_entry_id=str(configured_entry_id) if configured_entry_id else None,
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

        for month in months:
            self.logger.info("Exporting forecast month=%s", month)
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
            self.logger.info("Extracted %s forecast row(s) for month=%s", len(rows), month)
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
