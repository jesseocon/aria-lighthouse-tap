"""Load and validate config/properties/registry.yml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from lighthouse_connector import properties

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "properties" / "registry.yml"

REQUIRED_TOP_LEVEL = (
    "org_id",
    "bq_project_production",
    "bq_project_development",
    "source",
    "properties",
)
REQUIRED_PROPERTY_FIELDS = (
    "slug",
    "hotel_id",
    "production_property_id",
    "development_property_id",
)

VALID_ENVIRONMENTS = frozenset(properties.ENVIRONMENTS)


class RegistryError(ValueError):
    """Invalid or missing registry data."""


def load_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or REGISTRY_PATH
    if not registry_path.is_file():
        raise RegistryError(f"Registry not found: {registry_path}")

    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RegistryError("Registry root must be a mapping")

    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            raise RegistryError(f"Registry missing required key: {key}")

    properties = data["properties"]
    if not isinstance(properties, list) or not properties:
        raise RegistryError("Registry must include at least one property")

    slugs: set[str] = set()
    for index, prop in enumerate(properties):
        if not isinstance(prop, dict):
            raise RegistryError(f"Property at index {index} must be a mapping")
        for field in REQUIRED_PROPERTY_FIELDS:
            if field not in prop:
                raise RegistryError(
                    f"Property {prop.get('slug', index)!r} missing required field: {field}"
                )
        slug = str(prop["slug"])
        if slug in slugs:
            raise RegistryError(f"Duplicate property slug: {slug}")
        slugs.add(slug)

    return data


def list_slugs(path: Path | None = None) -> list[str]:
    registry = load_registry(path)
    return [str(prop["slug"]) for prop in registry["properties"]]


def get_property(slug: str, path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    for prop in registry["properties"]:
        if str(prop["slug"]) == slug:
            return {
                "org_id": registry["org_id"],
                "bq_project_production": registry["bq_project_production"],
                "bq_project_development": registry["bq_project_development"],
                "source": registry["source"],
                **prop,
            }
    raise RegistryError(f"Unknown property slug: {slug}")


def normalize_environment(environment: str) -> str:
    try:
        return properties.normalize_environment(environment)
    except properties.PropertyError as exc:
        raise RegistryError(str(exc)) from exc


def bronze_snapshot_daily_table(source: str, hotel_id: str) -> str:
    return properties.bronze_table(source, "strategy-snapshot", hotel_id)


def bronze_parity_list_table(source: str, hotel_id: str) -> str:
    return properties.bronze_table(source, "parity-list", hotel_id)


def bronze_budget_table(source: str, hotel_id: str) -> str:
    return properties.bronze_table(source, "budget", hotel_id)


def bronze_forecast_table(source: str, hotel_id: str) -> str:
    return properties.bronze_table(source, "forecast", hotel_id)


def bronze_rates_table(source: str, hotel_id: str) -> str:
    return properties.bronze_table(source, "rates", hotel_id)


bronze_dataset = properties.bronze_dataset
bronze_table_names = properties.bronze_table_names


def bronze_copy_spec(slug: str, path: Path | None = None) -> dict[str, Any]:
    """Bronze tables to copy from development to production after one scrape."""
    return properties.bronze_copy_spec(get_property(slug, path))


def property_id_for_environment(prop: dict[str, Any], environment: str) -> str:
    normalize_environment(environment)
    return properties.property_id_for_environment(prop, environment)


def bq_project_for_environment(prop: dict[str, Any], environment: str) -> str:
    normalize_environment(environment)
    return properties.bq_project_for_environment(prop, environment)
