"""Navigation for the Lighthouse rates compset table."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from tap_lighthouse.rates_export import wait_for_rates_table

# UI order: OTAs, then Brand.com. Best flex is the page default (no rateParam).
CHANNELS: tuple[tuple[str, str, str], ...] = (
    ("booking_com", "Booking.com", "bookingdotcom"),
    ("expedia", "Expedia", "expedia"),
    ("priceline", "Priceline", "priceline"),
    ("brand_com", "Brand.com", "branddotcom"),
)
RATE_TYPES: tuple[tuple[str, str, str | None], ...] = (
    ("best_flex", "Best flex", None),
    ("lowest_flex", "Lowest flex", "flex"),
    ("lowest", "Lowest", "lowest"),
    ("third_party", "3rd Party", "thirdparty"),
)
DEFAULT_RATE_TYPE_KEYS = ("best_flex",)
_RATE_TYPES_BY_KEY = {item[0]: item for item in RATE_TYPES}


def resolve_rate_types(raw: str | None = None) -> tuple[tuple[str, str, str | None], ...]:
    """Rate types to scrape. Default is Best flex. Pass a comma-separated list to add more."""
    text = (raw or "").strip()
    keys = DEFAULT_RATE_TYPE_KEYS if not text else tuple(part.strip() for part in text.split(",") if part.strip())
    unknown = [key for key in keys if key not in _RATE_TYPES_BY_KEY]
    if unknown:
        known = ", ".join(_RATE_TYPES_BY_KEY)
        msg = f"Unknown rates_rate_types {unknown}. Known: {known}"
        raise ValueError(msg)
    if not keys:
        msg = "rates_rate_types is empty"
        raise ValueError(msg)
    return tuple(_RATE_TYPES_BY_KEY[key] for key in keys)


def resolve_rates_url(
    hotel_id: str,
    *,
    month: str,
    ota_id: str,
    rate_param: str | None,
    los: int = 1,
    max_persons: int = 2,
    compset_id: int = 1,
    base_url: str = "https://app.mylighthouse.com",
) -> str:
    params = [
        f"compsetId={compset_id}",
        f"los={los}",
        f"maxPersons={max_persons}",
        f"month={month}",
        f"otaId={ota_id}",
    ]
    if rate_param:
        params.append(f"rateParam={rate_param}")
    params.append("view=table")
    return f"{base_url.rstrip('/')}/hotel/{hotel_id}/rates?{'&'.join(params)}"


def navigate_to_rates(
    page: Page,
    hotel_id: str,
    *,
    month: str,
    ota_id: str,
    rate_param: str | None,
    los: int = 1,
    max_persons: int = 2,
    compset_id: int = 1,
    base_url: str = "https://app.mylighthouse.com",
    timeout_ms: int = 60_000,
) -> str:
    url = resolve_rates_url(
        hotel_id,
        month=month,
        ota_id=ota_id,
        rate_param=rate_param,
        los=los,
        max_persons=max_persons,
        compset_id=compset_id,
        base_url=base_url,
    )
    page.goto(url, wait_until="domcontentloaded")
    wait_for_rates_table(page, timeout_ms=timeout_ms)
    return url
