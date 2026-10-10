"""Click Refresh rates once per page, then reload until the Updated label is newer."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

REFRESH_BUTTON_SELECTOR = "button.prism-button--primary:has-text('Refresh rates')"
LIVESHOP_PATH = "/apigateway/v1/app/liveshop"
RATES_PATH = "/apigateway/v1/app/rates/"

# A page already this fresh is not clicked again (e.g. a retry minutes later).
DEFAULT_RECENT_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 1200
DEFAULT_POLL_SECONDS = 15
# Rates GETs quiet this long after the shop counts as a finished reload.
DEFAULT_SETTLE_SECONDS = 20
# The in-place Updated label does not change after a shop; reload at least this often.
DEFAULT_RELOAD_SECONDS = 60

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
  const pattern = /^Updated\\s+(?:just now|a few seconds ago|a second ago|a minute ago|an hour ago|a day ago|\\d+\\s+(?:seconds?|minutes?|hours?|days?)\\s+ago)$/i;
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const candidates = [];
  for (const el of document.querySelectorAll("body *")) {
    if (el.children.length) continue;
    const text = normalize(el.textContent);
    if (pattern.test(text) && visible(el)) candidates.push({ el, text });
  }
  if (!candidates.length) return "";
  const button = Array.from(document.querySelectorAll("button")).find(
    (el) => /Refresh rates/i.test(normalize(el.textContent)) && visible(el),
  );
  if (!button || candidates.length === 1) return candidates[0].text;
  const anchor = button.getBoundingClientRect();
  const ax = anchor.left + anchor.width / 2;
  const ay = anchor.top + anchor.height / 2;
  let best = candidates[0];
  let bestDistance = Infinity;
  for (const candidate of candidates) {
    const rect = candidate.el.getBoundingClientRect();
    const dx = rect.left + rect.width / 2 - ax;
    const dy = rect.top + rect.height / 2 - ay;
    const distance = Math.hypot(dx, dy);
    if (distance < bestDistance) {
      best = candidate;
      bestDistance = distance;
    }
  }
  return best.text;
}
"""

READ_RATE_CELLS_JS = """
() => {
  const body = document.querySelector("div.rates-table-container table tbody");
  return body ? (body.innerText || "").replace(/\\s+/g, " ").trim() : "";
}
"""


@dataclass(frozen=True)
class RefreshObservation:
    """Snapshot time for one channel page, and the Updated label it came from."""

    refreshed_at: str
    refresh_label: str
    clicked: bool


class RatesRefreshTimeout(TimeoutError):
    """No reload showed a newer Updated label. The button was not clicked again."""


@dataclass
class ShopNetwork:
    """liveshop POST and the rates GETs that follow it, from page responses."""

    clock: Callable[[], float]
    liveshop_status: int | None = None
    liveshop_at: float | None = None
    rates_after_shop: int = 0
    last_rates_status: int | None = None
    last_rates_at: float | None = None
    _seen: list[str] = field(default_factory=list)

    def on_response(self, response: Any) -> None:  # noqa: ANN401
        try:
            url = str(response.url)
            method = str(response.request.method).upper()
            status = int(response.status)
        except Exception:  # noqa: BLE001 - best-effort capture
            return
        if LIVESHOP_PATH in url and method == "POST":
            self.liveshop_status = status
            self.liveshop_at = self.clock()
            return
        if RATES_PATH in url and method == "GET" and self.liveshop_at is not None:
            self.last_rates_status = status
            if status == 200:
                self.rates_after_shop += 1
                self.last_rates_at = self.clock()

    def settled(self, *, settle_seconds: float) -> bool:
        if self.liveshop_status != 200 or self.last_rates_at is None:
            return False
        return self.clock() - self.last_rates_at >= settle_seconds


def config_flag(value: object, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


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


def label_is_recent(label: str, *, recent_seconds: int) -> bool:
    age = updated_label_age_seconds(label)
    return age is not None and age <= recent_seconds


def label_is_newer(before: str, current: str) -> bool:
    """True when current reports a more recent shop than before."""
    age = updated_label_age_seconds(current)
    if age is None:
        return False
    before_age = updated_label_age_seconds(before)
    if before_age is None:
        return True
    return age < before_age


def snapshot_time(observed_at: datetime, label: str) -> datetime:
    """Observation time minus the age the label reports."""
    age = updated_label_age_seconds(label)
    return observed_at - timedelta(seconds=age or 0)


def observe_without_click(
    label: str,
    *,
    now: Callable[[], datetime] | None = None,
) -> RefreshObservation:
    clock = now or (lambda: datetime.now().astimezone())
    return RefreshObservation(
        refreshed_at=snapshot_time(clock(), label).isoformat(),
        refresh_label=label,
        clicked=False,
    )


def read_rates_updated_label(page: Page) -> str:
    label = page.evaluate(READ_UPDATED_LABEL_JS)
    return str(label or "").strip()


def read_rates_cells_text(page: Page) -> str:
    return str(page.evaluate(READ_RATE_CELLS_JS) or "")


def refresh_rates_page(
    page: Page,
    *,
    channel: str,
    reload: Callable[[], Any],
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    recent_seconds: int = DEFAULT_RECENT_SECONDS,
    settle_seconds: float = DEFAULT_SETTLE_SECONDS,
    reload_seconds: float = DEFAULT_RELOAD_SECONDS,
    logger: Any | None = None,  # noqa: ANN401
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] | None = None,
    read_label: Callable[[Page], str] = read_rates_updated_label,
    read_cells: Callable[[Page], str] = read_rates_cells_text,
) -> RefreshObservation:
    """Refresh one channel page and leave a freshly loaded page behind.

    Clicks the header button at most once, and only when it is enabled. A
    disabled button is left alone and the table already on the page is synced.
    The in-place page keeps its old Updated label after a shop, so completion
    is a reload whose label is newer than the label already on the page.
    Network and cell changes only decide when to reload. If the budget ends
    without a newer label, the table on the page is returned and the stream
    continues.
    """
    clock = now or (lambda: datetime.now().astimezone())
    tick = monotonic or time.monotonic
    # Playwright sync events only dispatch inside Playwright calls, not time.sleep.
    pause = sleep or (lambda seconds: page.wait_for_timeout(seconds * 1000))

    before = read_label(page)
    if label_is_recent(before, recent_seconds=recent_seconds):
        if logger is not None:
            logger.info("Rates refresh skipped channel=%s label=%s", channel, before)
        return observe_without_click(before, now=clock)

    if not _click_refresh_if_enabled(page, channel=channel, label=before, logger=logger):
        return observe_without_click(before, now=clock)

    network = ShopNetwork(clock=tick)
    page.on("response", network.on_response)
    try:
        baseline_cells = _safe_read(read_cells, page)
        started = tick()
        last_reload_at = started
        reloads = 0
        current = before

        while True:
            pause(poll_seconds)
            elapsed = tick() - started
            in_place_label = _safe_read(read_label, page)
            cells = _safe_read(read_cells, page)
            cells_changed = bool(cells) and bool(baseline_cells) and cells != baseline_cells
            settled = network.settled(settle_seconds=settle_seconds)
            since_reload = tick() - last_reload_at
            signal = reloads == 0 and (
                cells_changed or settled or label_is_newer(before, in_place_label)
            )
            timed_out = elapsed >= timeout_seconds
            reload_due = signal or since_reload >= reload_seconds or timed_out
            if logger is not None:
                logger.info(
                    "Rates refresh waiting channel=%s elapsed=%ss label=%s cells_changed=%s "
                    "liveshop=%s rates_after_shop=%s last_rates=%s reload_due=%s",
                    channel,
                    int(elapsed),
                    in_place_label or "missing",
                    cells_changed,
                    network.liveshop_status,
                    network.rates_after_shop,
                    network.last_rates_status,
                    reload_due,
                )
            if reload_due:
                reloads += 1
                last_reload_at = tick()
                try:
                    reload()
                except Exception as exc:  # noqa: BLE001 - retry the reload, not the click
                    if logger is not None:
                        logger.warning("Rates refresh reload failed channel=%s: %s", channel, exc)
                    current = ""
                else:
                    current = _safe_read(read_label, page)
                if label_is_newer(before, current):
                    return _finish(
                        clock,
                        current,
                        channel=channel,
                        clicked=True,
                        reloads=reloads,
                        logger=logger,
                    )
                if logger is not None:
                    logger.info(
                        "Rates refresh reload not newer channel=%s before=%s after=%s",
                        channel,
                        before,
                        current or "missing",
                    )
            if timed_out:
                if logger is not None:
                    logger.warning(
                        "Rates refresh gave up channel=%s after %ss label=%s clicked=%s",
                        channel,
                        int(timeout_seconds),
                        current or "missing",
                        True,
                    )
                return _observation(clock, current or before, clicked=True)
    finally:
        try:
            page.remove_listener("response", network.on_response)
        except Exception:  # noqa: BLE001, S110 - page may be closed
            pass


def _click_refresh_if_enabled(
    page: Page,
    *,
    channel: str,
    label: str,
    logger: Any | None,
) -> bool:
    """Click once when the button is enabled. Disabled means sync the page as it is."""
    button = page.locator(REFRESH_BUTTON_SELECTOR).first
    try:
        enabled = bool(button.is_enabled(timeout=5_000))
    except Exception as exc:  # noqa: BLE001 - missing or detached; scrape what is on the page
        if logger is not None:
            logger.info("Rates refresh button unavailable channel=%s: %s", channel, exc)
        return False
    if not enabled:
        if logger is not None:
            logger.info(
                "Rates refresh button disabled channel=%s label=%s; syncing current table",
                channel,
                label or "missing",
            )
        return False
    try:
        button.click(timeout=30_000)
    except Exception as exc:  # noqa: BLE001 - disabled again between the check and the click
        if type(exc).__name__ != "TimeoutError":
            raise
        if logger is not None:
            logger.info("Rates refresh click skipped channel=%s: %s", channel, exc)
        return False
    if logger is not None:
        logger.info("Rates refresh clicked channel=%s previous=%s", channel, label or "missing")
    return True


def _finish(
    clock: Callable[[], datetime],
    label: str,
    *,
    channel: str,
    clicked: bool,
    reloads: int,
    logger: Any | None,
) -> RefreshObservation:
    observed = _observation(clock, label, clicked=clicked)
    if logger is not None:
        logger.info(
            "Rates refresh finished channel=%s label=%s refreshed_at=%s reloads=%s clicked=%s",
            channel,
            label,
            observed.refreshed_at,
            reloads,
            clicked,
        )
    return observed


def _observation(clock: Callable[[], datetime], label: str, *, clicked: bool) -> RefreshObservation:
    return RefreshObservation(
        refreshed_at=snapshot_time(clock(), label).isoformat(),
        refresh_label=label,
        clicked=clicked,
    )


def _safe_read(reader: Callable[[Page], str], page: Page) -> str:
    try:
        return reader(page)
    except Exception:  # noqa: BLE001 - a failed read retries the read, not the click
        return ""
