"""Lighthouse tap entry point."""

from __future__ import annotations

import sys

from singer_sdk import typing as th

from singer_playwright.tap import PlaywrightTap
from tap_lighthouse import streams

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
            "budget_entry_id",
            th.StringType(nullable=False),
            title="Budget Entry ID",
            description="Lighthouse budget entryId URL parameter",
            default="19564",
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
            "forecast_entry_id",
            th.StringType(nullable=True),
            title="Forecast Entry ID",
            description=(
                "Optional Lighthouse forecast entryId. When omitted, resolved once per run "
                "from /hotel/{hotel_id}/forecast redirect."
            ),
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
    ).to_dict()

    @override
    def discover_streams(
        self,
    ) -> list[
        streams.StrategySnapshotStream
        | streams.ParityListStream
        | streams.BudgetStream
        | streams.ForecastStream
    ]:
        return [
            streams.StrategySnapshotStream(self),
            streams.ParityListStream(self),
            streams.BudgetStream(self),
            streams.ForecastStream(self),
        ]


if __name__ == "__main__":
    TapLighthouse.cli()
