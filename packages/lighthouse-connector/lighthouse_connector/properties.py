"""Property naming rules shared by the connector and the registry helpers."""

from __future__ import annotations

from typing import Any

DEFAULT_SOURCE = "mlt_lighthouse_ota"
DEFAULT_BQ_PROJECT_DEVELOPMENT = "hospitalityops-dev"
DEFAULT_BQ_PROJECT_PRODUCTION = "hospitalityops"
ENVIRONMENTS = ("development", "production")
STREAMS = (
    "strategy-snapshot-v2",
    "market-segments",
    "rate-plans",
    "length-of-stay",
    "room-type",
    "parity-list-v2",
    "rates-v2",
)
STRATEGY_SNAPSHOT_STREAM = "strategy-snapshot"

_ENVIRONMENT_ALIASES = {"dev": "development", "prod": "production"}
_BRONZE_SUFFIX = {
    "strategy-snapshot": "snapshot_daily",
    "parity-list": "parity_list",
    "budget": "budget",
    "forecast": "forecast",
    "rates": "rates",
    "strategy-snapshot-v2": "snapshot_daily_v2",
    "market-segments": "market_segments",
    "rate-plans": "rate_plans",
    "length-of-stay": "length_of_stay",
    "room-type": "room_type",
    "parity-list-v2": "parity_list_v2",
    "rates-v2": "rates_v2",
}
_BRONZE_ORDER = STREAMS


class PropertyError(ValueError):
    pass


def normalize_environment(environment: str) -> str:
    env = _ENVIRONMENT_ALIASES.get(environment.strip(), environment.strip())
    if env not in ENVIRONMENTS:
        raise PropertyError(
            f"Invalid environment: {environment!r} (expected development or production)"
        )
    return env


def bronze_table(source: str, stream: str, hotel_id: str) -> str:
    return f"{source}__{_BRONZE_SUFFIX[stream]}_hotel_{hotel_id}"


def bronze_dataset(org_id: str) -> str:
    return f"bronze_{org_id}"


def silver_dataset(org_id: str) -> str:
    return f"silver_{org_id}"


def bronze_table_names(source: str, hotel_id: str) -> list[str]:
    return [bronze_table(source, stream, hotel_id) for stream in _BRONZE_ORDER]


def bronze_model_selectors(prop: dict[str, Any], *, include_strategy_snapshot: bool) -> dict[str, str]:
    """Bronze table -> dbt selector for the models it feeds (`source:mlt_lighthouse_ota.rates_v2+`).

    The dbt source is named for the suffix; its identifier carries source and hotel.
    """
    source, hotel_id = str(prop["source"]), str(prop["hotel_id"])
    streams = [*_BRONZE_ORDER, *([STRATEGY_SNAPSHOT_STREAM] if include_strategy_snapshot else [])]
    return {
        bronze_table(source, stream, hotel_id): f"source:{DEFAULT_SOURCE}.{_BRONZE_SUFFIX[stream]}+"
        for stream in streams
    }


def stream_maps(prop: dict[str, Any]) -> dict[str, dict[str, str]]:
    source, hotel_id = str(prop["source"]), str(prop["hotel_id"])
    return {
        stream: {"__alias__": bronze_table(source, stream, hotel_id)}
        for stream in _BRONZE_ORDER
    }


def bronze_copy_spec(prop: dict[str, Any]) -> dict[str, Any]:
    """Bronze tables to copy from development to production after one scrape."""
    return {
        "source_project": str(prop["bq_project_development"]),
        "dest_project": str(prop["bq_project_production"]),
        "dataset": bronze_dataset(str(prop["org_id"])),
        "tables": bronze_table_names(str(prop["source"]), str(prop["hotel_id"])),
    }


def property_id_for_environment(prop: dict[str, Any], environment: str) -> str:
    if normalize_environment(environment) == "production":
        return str(prop["production_property_id"])
    return str(prop["development_property_id"])


def bq_project_for_environment(prop: dict[str, Any], environment: str) -> str:
    if normalize_environment(environment) == "production":
        return str(prop["bq_project_production"])
    return str(prop["bq_project_development"])


def dbt_vars(
    prop: dict[str, Any], environment: str, *, include_strategy_snapshot: bool
) -> dict[str, Any]:
    return {
        "bq_project": bq_project_for_environment(prop, environment),
        "org_id": prop["org_id"],
        "source": prop["source"],
        "property_id": property_id_for_environment(prop, environment),
        "property_slug": prop.get("property_slug") or prop["slug"],
        "hotel_id": str(prop["hotel_id"]),
        "include_strategy_snapshot": include_strategy_snapshot,
    }
