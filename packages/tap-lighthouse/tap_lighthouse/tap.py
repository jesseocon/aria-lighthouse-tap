"""Lighthouse tap entry point."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from singer_sdk import typing as th

from playwright.sync_api import sync_playwright

from singer_playwright.progress import report
from singer_playwright.screenshots import screenshot
from singer_playwright.tap import PlaywrightTap
from tap_lighthouse import signout
from tap_lighthouse.client import LighthouseStream
from tap_lighthouse.password_login import LoginRejected, apply_credentials
from tap_lighthouse import streams_v2

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class _PasswordBrowser:
    """Chromium with no saved session. The run types the username and password."""

    def __init__(self, playwright: object, browser: object, context: object, page: object) -> None:
        self._playwright = playwright
        self._browser = browser
        self.context = context
        self.page = page

    @classmethod
    def start(cls, config: dict, *, handoff: Path | None = None, logger: logging.Logger | None = None) -> _PasswordBrowser:
        """Sign in, or start signed in from a login chain's handed-over state when it still works."""
        username = config.get("username")
        password = config.get("password")
        login_url = config.get("login_url") or "https://app.mylighthouse.com/login"
        if not username or not password:
            raise LoginRejected("auth_method password requires username and password")
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=bool(config.get("headless", True)))
        if handoff is not None and handoff.is_file() and handoff.stat().st_size:
            context = browser.new_context(viewport={"width": 1600, "height": 1000}, storage_state=str(handoff))
            page = context.new_page()
            if not signout.session_closed(page):
                if logger is not None:
                    logger.info("Started signed in to Lighthouse with the previous run's session (no new sign-in)")
                return cls(playwright, browser, context, page)
            if logger is not None:
                logger.info("The handed-over Lighthouse session has ended; signing in with the password")
            context.close()
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        try:
            apply_credentials(
                page,
                username=str(username),
                password=str(password),
                login_url=str(login_url),
            )
        except Exception:
            context.close()
            browser.close()
            playwright.stop()
            raise
        if logger is not None:
            logger.info("Signed in to Lighthouse with the password")
        return cls(playwright, browser, context, page)

    def stop(self) -> None:
        self.context.close()
        self._browser.close()
        self._playwright.stop()


class TapLighthouse(PlaywrightTap):
    """Singer tap for Lighthouse (OTA Insight) via Playwright."""

    name = "tap-lighthouse"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "handoff_path",
            th.StringType(nullable=True),
            title="Login chain handoff",
            description="Login chain only: memory-only file for the signed-in browser state between runs.",
        ),
        th.Property(
            "storage_state_path",
            th.StringType(nullable=True),
            secret=True,
            title="Storage State Path",
            description="Path to Playwright storage_state.json. Used when auth_method is storage_state.",
        ),
        th.Property(
            "auth_method",
            th.StringType(nullable=False),
            allowed_values=["storage_state", "password"],
            default="storage_state",
            title="Auth Method",
            description="password types the username and password. storage_state replays a saved login.",
        ),
        th.Property(
            "login_url",
            th.StringType(nullable=False),
            default="https://app.mylighthouse.com/login",
            title="Login URL",
            description="Page to open when auth_method is password.",
        ),
        th.Property(
            "username",
            th.StringType(nullable=True),
            secret=True,
            title="Username",
            description="Lighthouse username. Used when auth_method is password.",
        ),
        th.Property(
            "password",
            th.StringType(nullable=True),
            secret=True,
            title="Password",
            description="Lighthouse password. Used when auth_method is password.",
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

    @property
    def handoff_path(self) -> Path | None:
        """Where a login chain hands the signed-in browser state between runs (password logins)."""
        raw = self.config.get("handoff_path")
        if not raw or self.config.get("auth_method") != "password":
            return None
        return Path(str(raw))

    @override
    def _ensure_browser_started(self) -> None:
        if self._browser_runtime is not None:
            return
        if self.config.get("auth_method") == "password":
            self._browser_runtime = _PasswordBrowser.start(self.config, handoff=self.handoff_path, logger=self.logger)
            self._session_verified = True
            return
        super()._ensure_browser_started()

    @override
    def sync_all(self) -> None:
        # singer-sdk has no teardown hook, so end the session here whether the sync finishes or fails.
        try:
            super().sync_all()
        finally:
            self.teardown()

    @override
    def teardown(self) -> None:
        runtime = self._browser_runtime
        password = self.config.get("auth_method") == "password"
        handoff = self.handoff_path
        if runtime is not None and self._session_verified and password and handoff is not None:
            # A login chain: hand the session to the next run; the chain logs out at its end.
            try:
                partial = handoff.with_name(handoff.name + ".part")
                runtime.context.storage_state(path=str(partial))
                os.replace(partial, handoff)
                self.logger.info("Handed the Lighthouse session to the next run (the login chain logs out at its end)")
            except Exception as exc:  # noqa: BLE001 - fall back to logging out here
                self.logger.warning("Could not hand the Lighthouse session on (%s); logging out instead", exc)
                handoff = None
        if runtime is not None and self._session_verified and password and handoff is None:
            # Password logins end their own session; a console-saved session is left alone.
            try:
                self.logger.info("Signed out of Lighthouse (%s)", signout.sign_out(runtime.page))
            except Exception as exc:  # noqa: BLE001 - closing the browser still has to happen
                message = f"Signing out of Lighthouse failed, closing the browser anyway: {exc}"
                self.logger.warning("%s", message)
                screenshot(runtime.page, "Lighthouse sign-out failed", self.logger)
                report(self.logger, "warning", message=message, code="sign_out_failed")
        # PlaywrightTap.teardown ends in super().teardown(), which singer-sdk's Tap does not have.
        if runtime is not None:
            runtime.stop()
            self._browser_runtime = None
            self._session_verified = False

    @override
    def discover_streams(self) -> list[LighthouseStream]:
        return [
            streams_v2.StrategySnapshotV2Stream(self),
            streams_v2.MarketSegmentsStream(self),
            streams_v2.RatePlansStream(self),
            streams_v2.LengthOfStayStream(self),
            streams_v2.RoomTypeStream(self),
            streams_v2.ParityListV2Stream(self),
            streams_v2.RatesV2Stream(self),
        ]


if __name__ == "__main__":
    TapLighthouse.cli()
