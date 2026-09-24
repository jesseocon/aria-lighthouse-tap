"""Fixed parity channel keys and human labels for viz metadata."""

from __future__ import annotations

from typing import Any

PARITY_CHANNEL_DEFINITIONS: tuple[dict[str, str], ...] = (
    {"key": "brand_com", "label": "Brand.com", "role": "ota"},
    {"key": "booking_com", "label": "Booking.com", "role": "ota"},
    {"key": "expedia", "label": "Expedia", "role": "ota"},
    {"key": "priceline", "label": "Priceline", "role": "ota"},
    {"key": "loss_channels_on_metasearch", "label": "Loss channels on metasearch", "role": "metasearch"},
    {"key": "lowest_rate", "label": "Lowest rate", "role": "summary"},
)

PARITY_CHANNEL_KEYS: tuple[str, ...] = tuple(item["key"] for item in PARITY_CHANNEL_DEFINITIONS)

DROPPED_PARITY_FIELDS: frozenset[str] = frozenset({"column_7", "column_7_has_tooltip"})


def build_parity_entity_labels() -> dict[str, str]:
    return {item["key"]: item["label"] for item in PARITY_CHANNEL_DEFINITIONS}


def parity_channel_dimensions_for_registry() -> list[dict[str, str]]:
    return [dict(item) for item in PARITY_CHANNEL_DEFINITIONS]
