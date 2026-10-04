"""Click Refresh rates once per page, then poll the Updated label until it is recent."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

REFRESH_BUTTON_SELECTOR = "button.prism-button--primary:has-text('Refresh rates')"

# Shop completion is "a few seconds ago", not the first liveshop 200.
# 10 minutes still counts when a poll lands after the label has ticked forward.
DEFAULT_RECENT_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 1200
DEFAULT_POLL_SECONDS = 15

_UPDATED_PREFIX = re.compile(r"^updated\s+(?P<rest>.+)$", re.IGNORECASE)
_RELATIVE_AGE = re.compile(
    r"^(?P<count>\d+)\s+(?P<unit>seconds?|minutes?|hours?|days?)\s+ago$",
    re.IGNORECASE,
)
_UNIT_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}

READ_UPDATED_LABEL_JS = """
() => {
  const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim();
  const nodes = document.querySelectorAll("span, div, p, small, time");
  let best = "";
  for (const el of nodes) {
    if (el.children.length) continue;
    const text = normalize(el.textContent);
    if (!/^Updated\\s+/i.test(text) || text.length > 80) continue;
    if (!best || text.length < best.length) best = text;
  }
  if (best) return best;
  const body = normalize(document.body && document.body.innerText);
  const match = body.match(
    /Updated\\s+(?:just now|a few seconds ago|a second ago|a minute ago|an hour ago|a day ago|\\d+\\s+(?:seconds?|minutes?|hours?|days?)\\s+ago)/i,
  );
  return match ? match[0] : "";
}
"""


@dataclass(frozen=True)
class RefreshObservation:
    """When we accepted the page as a snapshot, and the label we read."""

    refreshed_at: str
    refresh_label: str
    clicked: bool


class RatesRefreshTimeout(TimeoutError):
    """The Updated label never became recent. The button was not clicked again."""


def updated_label_age_seconds(label: str) -> int | None:
    """Age implied by an Updated label. None when the text is not a relative time."""
    text = re.sub(r"\s+", " ", label).strip()
    match = _UPDATED_PREFIX.match(text)
    if match is None:
        return None
    rest = match.group("rest").rstrip(".").lower()
    if rest in {"just now", "a few seconds ago", "a second ago", "seconds ago"}:
        return 0
    if rest == "a minute ago":
        return 60
    if rest == "an hour ago":
        return 3600
    if rest == "a day ago":
        return 86400
    relative = _RELATIVE_AGE.match(rest)
    if relative is None:
        return None
    unit = relative.group("unit").lower().removesuffix("s")
    return int(relative.group("count")) * _UNIT_SECONDS[unit]


def config_flag(value: object, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def label_is_recent(label: str, *, recent_seconds: int) -> bool:
    age = updated_label_age_seconds(label)
    return age is not None and age <= recent_seconds


def refresh_completed(before: str, current: str, *, recent_seconds: int) -> bool:
    """True when the label moved to a newer time inside the recent window."""
    if not current or current == before:
        return False
    age = updated_label_age_seconds(current)
    if age is None or age > recent_seconds:
        return False
    before_age = updated_label_age_seconds(before)
    if before_age is None:
        return True
    return age < before_age


def read_rates_updated_label(page: Page) -> str:
    label = page.evaluate(READ_UPDATED_LABEL_JS)
    return str(label or "").strip()


def refresh_rates_page(
    page: Page,
    *,
    channel: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    recent_seconds: int = DEFAULT_RECENT_SECONDS,
    logger: Any | None = None,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] | None = None,
) -> RefreshObservation:
    """Refresh one channel page.

    Clicks the header button at most once. Later attempts only re-read the
    Updated label. A label that is already recent skips the click.
    """
    clock = now or (lambda: datetime.now().astimezone())
    pause = sleep or time.sleep
    tick = monotonic or time.monotonic
    before = read_rates_updated_label(page)
    if label_is_recent(before, recent_seconds=recent_seconds):
        if logger is not None:
            logger.info(
                "Rates refresh skipped channel=%s label=%s",
                channel,
                before,
            )
        return RefreshObservation(
            refreshed_at=clock().isoformat(),
            refresh_label=before,
            clicked=False,
        )

    page.locator(REFRESH_BUTTON_SELECTOR).first.click(timeout=30_000)
    if logger is not None:
        logger.info("Rates refresh clicked channel=%s previous=%s", channel, before)

    deadline = tick() + timeout_seconds
    while True:
        try:
            current = read_rates_updated_label(page)
        except Exception as exc:  # noqa: BLE001 - retry the read, not the click
            if logger is not None:
                logger.warning("Rates refresh poll failed channel=%s: %s", channel, exc)
            current = ""
        if refresh_completed(before, current, recent_seconds=recent_seconds):
            if logger is not None:
                logger.info("Rates refresh finished channel=%s label=%s", channel, current)
            return RefreshObservation(
                refreshed_at=clock().isoformat(),
                refresh_label=current,
                clicked=True,
            )
        remaining = deadline - tick()
        if remaining <= 0:
            msg = (
                f"Rates refresh timed out for {channel} after {timeout_seconds}s. "
                f"Last label: {current or before or 'missing'}"
            )
            raise RatesRefreshTimeout(msg)
        pause(min(poll_seconds, remaining))
