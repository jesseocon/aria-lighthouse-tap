"""Lighthouse tap entry point."""

from __future__ import annotations

import sys

from singer_sdk import typing as th

from singer_playwright.tap import PlaywrightTap
from tap_lighthouse import streams, streams_v2

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class TapLighthouse(PlaywrightTap):
    """Singer tap for Lighthouse (OTA Insight) via Playwright."""

    name = "tap-lighthouse"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "storage_state_path",
            th.StringType(nullable=False),
            required=True,
            secret=True,
            title="Storage State Path",
            description="Path to Playwright storage_state.json saved after manual login",
        ),
        th.Property(
            "hotel_id",
            th.StringType(nullable=False),
            required=True,
            title="Hotel ID",
            description="Lighthouse property hotel id (numeric)",
        ),
        th.Property(
            "base_url",
            th.StringType(nullable=False),
            title="Base URL",
            default="https://app.mylighthouse.com",
        ),
        th.Property(
            "session_probe_url",
            th.StringType(nullable=False),
            title="Session Probe URL",
            default="https://app.mylighthouse.com/",
        ),
        th.Property(
            "headless",
            th.BooleanType(nullable=False),
            title="Headless",
            default=True,
        ),
        th.Property(
            "rate_limit_seconds",
            th.NumberType(nullable=False),
            title="Rate Limit Seconds",
            default=5.0,
        ),
        th.Property(
            "start_date",
            th.DateType(nullable=True),
            title="Start Date",
            description="Earliest as_of_date for strategy-snapshot on first sync",
        ),
        th.Property(
            "end_date",
            th.DateType(nullable=True),
            title="End Date",
            description="Latest as_of_date for strategy-snapshot (defaults to today)",
        ),
        th.Property(
            "window_days",
            th.IntegerType(nullable=False),
            title="Snapshot Window Days",
            default=365,
        ),
        th.Property(
            "lookback_days",
            th.IntegerType(nullable=False),
            title="Lookback Days",
            description="Days to re-sync on incremental runs",
            default=7,
        ),
        th.Property(
            "parity_los",
            th.IntegerType(nullable=False),
            title="Parity Length of Stay",
            default=1,
        ),
        th.Property(
            "parity_max_persons",
            th.IntegerType(nullable=False),
            title="Parity Max Persons",
            default=2,
        ),
        th.Property(
            "parity_forward_months",
            th.IntegerType(nullable=False),
            title="Parity Forward Months",
            description=(
                "Months after the current month to scrape on every sync. "
                "Default 2 covers current, next, and next+1."
            ),
            default=2,
        ),
        th.Property(
            "parity_hover_delay_ms",
            th.IntegerType(nullable=False),
            title="Parity Hover Delay Ms",
            default=300,
        ),
        th.Property(
            "rates_forward_months",
            th.IntegerType(nullable=False),
            title="Rates Forward Months",
            description=(
                "Months after the current month to scrape for rates. "
                "Default 1 covers the current month and the next month."
            ),
            default=1,
        ),
        th.Property(
            "rates_rate_types",
            th.StringType(nullable=False),
            title="Rates Rate Types",
            description=(
                "Comma-separated rate types to scrape. Default is best_flex. "
                "Also: lowest_flex, lowest, third_party."
            ),
            default="best_flex",
        ),
        th.Property(
            "rates_refresh",
            th.BooleanType(nullable=False),
            title="Rates Refresh",
            description=(
                "Click Refresh rates once on each channel page before scraping. "
                "A page that already says it updated within rates_refresh_recent_seconds "
                "is not clicked again."
            ),
            default=True,
        ),
        th.Property(
            "rates_refresh_timeout_seconds",
            th.IntegerType(nullable=False),
            title="Rates Refresh Timeout Seconds",
            description=(
                "How long to poll the Updated label after one click. "
                "The button is not pressed again."
            ),
            default=1200,
        ),
        th.Property(
            "rates_refresh_poll_seconds",
            th.IntegerType(nullable=False),
            title="Rates Refresh Poll Seconds",
            description="Seconds between Updated-label reads while a refresh is running.",
            default=15,
        ),
        th.Property(
            "rates_refresh_recent_seconds",
            th.IntegerType(nullable=False),
            title="Rates Refresh Recent Seconds",
            description=(
                "Skip the click when the label is already this recent, and treat a "
                "label this recent as the shop having finished."
            ),
            default=600,
        ),
        th.Property(
            "budget_variance",
            th.StringType(nullable=False),
            title="Budget Variance Mode",
            description="Variance display mode (absolute, percentage, or none)",
            default="absolute",
        ),
        th.Property(
            "budget_start_month",
            th.StringType(nullable=True),
            title="Budget Start Month",
            description="First YYYY-MM month on full sync (e.g. 2020-01). Defaults to current month.",
        ),
        th.Property(
            "budget_forward_months",
            th.IntegerType(nullable=False),
            title="Budget Forward Months",
            description="Months after the current month to scrape on every sync",
            default=2,
        ),
        th.Property(
            "forecast_start_month",
            th.StringType(nullable=True),
            title="Forecast Start Month",
            description="First YYYY-MM month on full sync (e.g. 2020-01). Defaults to current month.",
        ),
        th.Property(
            "forecast_forward_months",
            th.IntegerType(nullable=False),
            title="Forecast Forward Months",
            description="Months after the current month to scrape on every sync",
            default=2,
        ),
        th.Property(
            "api_pause_min_seconds",
            th.NumberType(nullable=False),
            title="API Pause Min Seconds",
            description="v2 streams: shortest random pause between API batches.",
            default=4,
        ),
        th.Property(
            "api_pause_max_seconds",
            th.NumberType(nullable=False),
            title="API Pause Max Seconds",
            description="v2 streams: longest random pause between API batches.",
            default=9,
        ),
        th.Property(
            "strategy_v2_pickup_days",
            th.IntegerType(nullable=False),
            title="Strategy v2 Pickup Days",
            description="strategy-snapshot-v2: pickup and variance compare date is as-of minus this many days (page default 7).",
            default=7,
        ),
        th.Property(
            "strategy_v2_max_as_of_dates",
            th.IntegerType(nullable=False),
            title="Strategy v2 Max As-of Dates",
            description="strategy-snapshot-v2: cap as-of dates per run for backfills (0 = no cap). The bookmark resumes next run.",
            default=0,
        ),
        th.Property(
            "rates_v2_refresh",
            th.BooleanType(nullable=False),
            title="Rates v2 Refresh",
            description=(
                "rates-v2: click Refresh rates (live shop) once per month and channel before the API calls. "
                "Off by default; v2 reads the latest shopped rates."
            ),
            default=False,
        ),
    ).to_dict()

    @override
    def discover_streams(self) -> list[streams.LighthouseStream]:
        return [
            streams.StrategySnapshotStream(self),
            streams.ParityListStream(self),
            streams.RatesStream(self),
            streams.BudgetStream(self),
            streams.ForecastStream(self),
            streams_v2.StrategySnapshotV2Stream(self),
            streams_v2.ParityListV2Stream(self),
            streams_v2.RatesV2Stream(self),
        ]


if __name__ == "__main__":
    TapLighthouse.cli()
