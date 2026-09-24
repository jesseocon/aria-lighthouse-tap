"""Load and validate config/properties/registry.yml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "properties" / "registry.yml"

REQUIRED_TOP_LEVEL = ("org_id", "bq_project", "source", "properties")
REQUIRED_PROPERTY_FIELDS = (
    "slug",
    "hotel_id",
    "prod_property_id",
    "dev_property_id",
    "subject_entity_key",
    "pivot_parent_group_slug",
    "rate_shop_dimensions",
    "parity_channel_dimensions",
)


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

        dimensions = prop["rate_shop_dimensions"]
        if not isinstance(dimensions, list) or not dimensions:
            raise RegistryError(f"Property {slug!r} must have rate_shop_dimensions list")

        parity_channels = prop["parity_channel_dimensions"]
        if not isinstance(parity_channels, list) or not parity_channels:
            raise RegistryError(f"Property {slug!r} must have parity_channel_dimensions list")
        for channel in parity_channels:
            if not isinstance(channel, dict):
                raise RegistryError(f"Property {slug!r} parity_channel_dimensions entries must be mappings")
            for field in ("key", "label", "role"):
                if field not in channel:
                    raise RegistryError(
                        f"Property {slug!r} parity channel missing required field: {field}"
                    )

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
                "bq_project": registry["bq_project"],
                "source": registry["source"],
                **prop,
            }
    raise RegistryError(f"Unknown property slug: {slug}")


def bronze_snapshot_daily_table(source: str, hotel_id: str) -> str:
    return f"{source}__snapshot_daily_hotel_{hotel_id}"


def bronze_parity_list_table(source: str, hotel_id: str) -> str:
    return f"{source}__parity_list_hotel_{hotel_id}"


def bronze_budget_table(source: str, hotel_id: str) -> str:
    return f"{source}__budget_hotel_{hotel_id}"


def bronze_forecast_table(source: str, hotel_id: str) -> str:
    return f"{source}__forecast_hotel_{hotel_id}"


def property_id_for_tier(prop: dict[str, Any], tier: str) -> str:
    if tier == "prod":
        return str(prop["prod_property_id"])
    if tier == "dev":
        return str(prop["dev_property_id"])
    raise RegistryError(f"Unknown tier: {tier!r} (expected prod or dev)")
