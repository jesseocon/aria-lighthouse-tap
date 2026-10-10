"""Refresh rates: one click, reload until the Updated label is newer."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from tap_lighthouse.rates_refresh import (
    label_is_newer,
    label_is_recent,
    refresh_rates_page,
    updated_label_age_seconds,
)

PACIFIC = ZoneInfo("America/Los_Angeles")
OBSERVED_AT = datetime(2026, 10, 4, 16, 15, tzinfo=PACIFIC)


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


class _Locator:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    @property
    def first(self) -> _Locator:
        return self

    def is_enabled(self, timeout: int = 5_000) -> bool:
        return self.page.enabled

    def click(self, timeout: int = 30_000) -> None:
        self.page.clicks += 1


class FakePage:
    """In-place label stays stale. Only reload() swaps in the server label."""

    def __init__(self, *, label: str, cells: str = "199 189") -> None:
        self.label = label
        self.cells = cells
        self.clicks = 0
        self.reloads = 0
        self.enabled = True
        self.handlers: list = []
        self.server_label = label
        self.server_cells = cells

    def locator(self, _selector: str) -> _Locator:
        return _Locator(self)

    def on(self, event: str, handler) -> None:  # noqa: ANN001
        assert event == "response"
        self.handlers.append(handler)

    def remove_listener(self, event: str, handler) -> None:  # noqa: ANN001
        self.handlers.remove(handler)

    def reload(self) -> None:
        self.reloads += 1
        self.label = self.server_label
        self.cells = self.server_cells

    def respond(self, method: str, url: str, status: int = 200) -> None:
        response = SimpleNamespace(url=url, status=status, request=SimpleNamespace(method=method))
        for handler in list(self.handlers):
            handler(response)


def _run(page: FakePage, clock: _Clock, *, on_poll=None, **kwargs):  # noqa: ANN001, ANN003, ANN202
    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        if on_poll is not None:
            on_poll(page, clock)

    return refresh_rates_page(
        page,  # type: ignore[arg-type]
        channel="Booking.com",
        reload=page.reload,
        now=lambda: OBSERVED_AT,
        sleep=sleep,
        monotonic=clock.monotonic,
        read_label=lambda p: p.label,
        read_cells=lambda p: p.cells,
        **kwargs,
    )


def test_updated_label_age_parses_relative_times() -> None:
    assert updated_label_age_seconds("Updated a few seconds ago") == 0
    assert updated_label_age_seconds("Updated just now") == 0
    assert updated_label_age_seconds("Updated a minute ago") == 60
    assert updated_label_age_seconds("Updated 12 minutes ago") == 720
    assert updated_label_age_seconds("Updated 3 hours ago") == 3 * 3600
    assert updated_label_age_seconds("") is None
    assert label_is_recent("Updated 8 minutes ago", recent_seconds=600)
    assert not label_is_recent("Updated 3 hours ago", recent_seconds=600)
    assert label_is_newer("Updated 3 hours ago", "Updated 12 minutes ago")
    assert not label_is_newer("Updated 3 hours ago", "Updated 3 hours ago")


def test_skip_click_when_page_is_already_recent() -> None:
    page = FakePage(label="Updated 2 minutes ago")
    observed = _run(page, _Clock())
    assert page.clicks == 0
    assert page.reloads == 0
    assert observed.clicked is False
    assert observed.refreshed_at == (OBSERVED_AT - timedelta(minutes=2)).isoformat()


def test_stale_in_place_label_with_changed_cells_finishes_after_reload() -> None:
    page = FakePage(label="Updated 3 hours ago")

    def shop_finishes(p: FakePage, clock: _Clock) -> None:
        if clock.t >= 30 and p.cells == "199 189":
            p.cells = "198 180"
            p.server_label = "Updated 12 minutes ago"
            p.server_cells = "198 180"

    observed = _run(page, _Clock(), on_poll=shop_finishes, poll_seconds=15)
    assert page.clicks == 1
    assert page.reloads == 1
    assert observed.clicked is True
    assert observed.refresh_label == "Updated 12 minutes ago"
    assert observed.refreshed_at == (OBSERVED_AT - timedelta(minutes=12)).isoformat()
    assert page.handlers == []


def test_identical_cells_after_quiet_rates_reload_still_finishes() -> None:
    page = FakePage(label="Updated 3 hours ago")

    def network(p: FakePage, clock: _Clock) -> None:
        if clock.t == 15:
            p.respond("POST", "https://app.mylighthouse.com/apigateway/v1/app/liveshop?subscription_id=1")
            p.respond("GET", "https://app.mylighthouse.com/apigateway/v1/app/rates/?ota=bookingdotcom")
            p.server_label = "Updated a few seconds ago"

    observed = _run(
        page,
        _Clock(),
        on_poll=network,
        poll_seconds=15,
        settle_seconds=10,
        reload_seconds=600,
    )
    assert page.clicks == 1
    assert page.reloads == 1
    assert observed.refresh_label == "Updated a few seconds ago"
    assert observed.refreshed_at == OBSERVED_AT.isoformat()


def test_reload_not_newer_keeps_polling_without_second_click() -> None:
    page = FakePage(label="Updated 3 hours ago")

    def late_shop(p: FakePage, clock: _Clock) -> None:
        if clock.t >= 150:
            p.server_label = "Updated 2 minutes ago"

    observed = _run(page, _Clock(), on_poll=late_shop, poll_seconds=15, reload_seconds=60)
    assert page.clicks == 1
    assert page.reloads >= 2
    assert observed.refresh_label == "Updated 2 minutes ago"


def test_failed_reload_is_retried_without_second_click() -> None:
    page = FakePage(label="Updated 3 hours ago")
    page.server_label = "Updated 1 minute ago"
    attempts = {"n": 0}
    original = page.reload

    def flaky_reload() -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            msg = "Timed out waiting for the rates table"
            raise TimeoutError(msg)
        original()

    clock = _Clock()
    observed = refresh_rates_page(
        page,  # type: ignore[arg-type]
        channel="Expedia",
        reload=flaky_reload,
        poll_seconds=15,
        reload_seconds=30,
        now=lambda: OBSERVED_AT,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        read_label=lambda p: p.label,
        read_cells=lambda p: p.cells,
    )
    assert page.clicks == 1
    assert attempts["n"] == 2
    assert observed.refresh_label == "Updated 1 minute ago"


def test_timeout_returns_the_table_on_the_page_without_second_click() -> None:
    page = FakePage(label="Updated 3 hours ago")
    observed = _run(page, _Clock(), timeout_seconds=45, poll_seconds=15, reload_seconds=600)
    assert page.clicks == 1
    assert page.reloads == 1
    assert page.handlers == []
    assert observed.clicked is True
    assert observed.refresh_label == "Updated 3 hours ago"


def test_disabled_button_syncs_the_page_without_waiting() -> None:
    page = FakePage(label="Updated a day ago")
    page.enabled = False
    observed = _run(page, _Clock(), timeout_seconds=45, poll_seconds=15, reload_seconds=30)
    assert page.clicks == 0
    assert page.reloads == 0
    assert observed.clicked is False
    assert observed.refresh_label == "Updated a day ago"
    assert observed.refreshed_at == (OBSERVED_AT - timedelta(days=1)).isoformat()
