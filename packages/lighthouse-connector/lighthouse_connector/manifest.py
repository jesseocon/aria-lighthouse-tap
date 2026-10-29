"""Connector manifest: what Aria renders as the connection form and the run options."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from lighthouse_connector.properties import ENVIRONMENTS, STREAMS

KEY = "lighthouse"
JOB_NAME = "aria-connector-lighthouse"
LOGIN_URL = "https://app.mylighthouse.com/login"
PROBE_URL = "https://app.mylighthouse.com/"
RATE_TYPES = ("best_flex", "lowest_flex", "lowest", "third_party")


def _version() -> str:
    try:
        return version("lighthouse-connector")
    except PackageNotFoundError:
        return "0.0.0"


def _int(title: str, default: int, minimum: int = 0, maximum: int | None = None, **extra: Any):  # noqa: ANN202
    schema: dict[str, Any] = {"type": "integer", "title": title, "default": default, "minimum": minimum}
    if maximum is not None:
        schema["maximum"] = maximum
    return {**schema, **extra}


MONTH = {"type": "string", "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"}
DATE = {"type": "string", "format": "date", "pattern": r"^\d{4}-\d{2}-\d{2}$"}

TAP_SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "title": "Scraper settings",
    "additionalProperties": False,
    "default": {},
    "properties": {
        "start_date": {**DATE, "title": "First as-of date (first sync only)"},
        "window_days": _int("Strategy snapshot window (days)", 365, 1, 730),
        "lookback_days": _int("Incremental lookback (days)", 7, 0, 90),
        "rate_limit_seconds": _int("Seconds between page actions", 5, 0, 60),
        "parity_los": _int("Parity length of stay", 1, 1, 30),
        "parity_max_persons": _int("Parity guests", 2, 1, 8),
        "parity_forward_months": _int("Parity months ahead", 2, 0, 12),
        "parity_hover_delay_ms": _int("Parity hover delay (ms)", 300, 0, 5000),
        "rates_forward_months": _int("Rates months ahead", 1, 0, 12),
        "rates_rate_types": {
            "type": "array",
            "title": "Rate types",
            "items": {"enum": list(RATE_TYPES)},
            "minItems": 1,
            "uniqueItems": True,
            "default": ["best_flex"],
        },
        "rates_refresh": {
            "type": "boolean",
            "title": "Refresh rates before reading each channel",
            "default": True,
        },
        "rates_refresh_timeout_seconds": _int("Refresh timeout (s)", 1200, 60, 7200),
        "rates_refresh_poll_seconds": _int("Refresh poll interval (s)", 15, 1, 300),
        "rates_refresh_recent_seconds": _int("Skip refresh when updated within (s)", 600, 0, 7200),
        "budget_variance": {
            "type": "string",
            "title": "Budget variance mode",
            "default": "absolute",
        },
        "budget_start_month": {**MONTH, "title": "Budget first month (YYYY-MM)"},
        "budget_forward_months": _int("Budget months ahead", 2, 0, 24),
        "forecast_start_month": {**MONTH, "title": "Forecast first month (YYYY-MM)"},
        "forecast_forward_months": _int("Forecast months ahead", 2, 0, 24),
        "events_days_back": _int("Events and holidays: days back", 365, 0, 730),
        "events_days_forward": _int("Events and holidays: days ahead", 365, 0, 730),
        "demand_days_forward": _int("Demand days ahead", 90, 1, 365),
        "smart_insights_rate_type": {
            "type": "string",
            "title": "Smart Insights rate type",
            "enum": ["lowest", "best_flex", "lowest_flex"],
            "default": "lowest",
        },
        "smart_insights_ota": {"type": "string", "title": "Smart Insights OTA", "default": "bookingdotcom"},
        "ranking_otas": {
            "type": "array",
            "title": "Daily ranking OTAs",
            "items": {"enum": ["bookingdotcom", "expedia"]},
            "minItems": 1,
            "uniqueItems": True,
            "default": ["bookingdotcom", "expedia"],
        },
        "rate_strategy_backfill_weeks": _int("Rate strategy weeks of history (first sync)", 52, 1, 52),
    },
}

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "title": "Lighthouse property",
    "additionalProperties": False,
    "required": [
        "org_id",
        "hotel_id",
        "development_property_id",
        "production_property_id",
    ],
    "properties": {
        "org_id": {
            "type": "string",
            "title": "Organization id",
            "description": "Aria organization this hotel belongs to. This runner serves every organization.",
            "pattern": r"^\d+$",
        },
        "hotel_id": {"type": "string", "title": "Lighthouse hotel id", "pattern": r"^\d+$"},
        "development_property_id": {"type": "string", "title": "Aria property id (development)"},
        "production_property_id": {"type": "string", "title": "Aria property id (production)"},
        "streams": {
            "type": "array",
            "title": "Streams",
            "items": {"enum": list(STREAMS)},
            "minItems": 1,
            "uniqueItems": True,
            "default": ["strategy-snapshot-v2"],
        },
        "environments": {
            "type": "array",
            "title": "Warehouses",
            "description": "Both: scrape once into development, copy bronze to production.",
            "items": {"enum": list(ENVIRONMENTS)},
            "minItems": 1,
            "uniqueItems": True,
            "default": list(ENVIRONMENTS),
        },
        "dbt_test": {"type": "boolean", "title": "Run dbt tests", "default": False},
        "tap": TAP_SETTINGS_SCHEMA,
    },
}

RUN_PARAMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "environment": {
            "enum": list(ENVIRONMENTS),
            "title": "Only this warehouse",
        },
        "start_date": {**DATE, "title": "Backfill from as-of date"},
        "end_date": {**DATE, "title": "Backfill to as-of date"},
        "keep_state": {
            "type": "boolean",
            "title": "Keep bookmarks during a date-range backfill",
            "default": False,
        },
        "scrape_only": {"type": "boolean", "title": "Load bronze only", "default": False},
        "transform_only": {"type": "boolean", "title": "Run dbt only", "default": False},
        "dbt_test": {"type": "boolean", "title": "Run dbt tests"},
    },
    "dependentRequired": {"end_date": ["start_date"]},
    "not": {
        "properties": {"scrape_only": {"const": True}, "transform_only": {"const": True}},
        "required": ["scrape_only", "transform_only"],
    },
}


def manifest() -> dict[str, Any]:
    return {
        "key": KEY,
        "display_name": "Lighthouse",
        "logo": "/logos/lighthouse.png",
        "version": _version(),
        "description": "Lighthouse (OTA Insight) rates, parity, strategy, events, demand, OTA rankings, and rate strategy.",
        # Room for a login's queue in one chain (Lighthouse runs take 15-50 minutes each).
        "job": {"name": JOB_NAME, "timeout_seconds": 12 * 3600},
        "progress": "v1",
        # One sign-in for a login's queue: runs hand the session on in memory, the chain logs out.
        "chain_login_runs": True,
        "auth": {
            "kind": "password",
            "fields": [
                {
                    "key": "username",
                    "title": "Username",
                    "secret": False,
                    "env": "TAP_LIGHTHOUSE_USERNAME",
                },
                {
                    "key": "password",
                    "title": "Password",
                    "secret": True,
                    "env": "TAP_LIGHTHOUSE_PASSWORD",
                },
            ],
            "optional_when_params": {"transform_only": True},
        },
        "config_schema": CONFIG_SCHEMA,
        "run_params_schema": RUN_PARAMS_SCHEMA,
    }
