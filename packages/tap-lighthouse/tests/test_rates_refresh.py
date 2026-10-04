"""Refresh-rates click once, then poll the Updated label."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tap_lighthouse.rates_refresh import (
    RatesRefreshTimeout,
    label_is_recent,
    refresh_rates_page,
    updated_label_age_seconds,
)

PACIFIC = ZoneInfo("America/Los_Angeles")
OBSERVED_AT = datetime(2026, 10, 4, 12, 53, tzinfo=PACIFIC)


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

    def click(self, timeout: int = 30_000) -> None:
        self.page.clicks += 1
        self.page.click_timeout = timeout


class FakePage:
    def __init__(self, labels: list[str], *, fail_on: set[int] | None = None) -> None:
        self.labels = list(labels)
        self.fail_on = fail_on or set()
        self.clicks = 0
        self.click_timeout = 0
        self.reads = 0

    def evaluate(self, _script: str) -> str:
        self.reads += 1
        if self.reads in self.fail_on:
            msg = "page navigating"
            raise RuntimeError(msg)
        if len(self.labels) > 1:
            return self.labels.pop(0)
        return self.labels[0]

    def locator(self, _selector: str) -> _Locator:
        return _Locator(self)


def test_updated_label_age_parses_relative_times() -> None:
    assert updated_label_age_seconds("Updated a few seconds ago") == 0
    assert updated_label_age_seconds("Updated just now") == 0
    assert updated_label_age_seconds("Updated a minute ago") == 60
    assert updated_label_age_seconds("Updated 15 hours ago") == 15 * 3600
    assert updated_label_age_seconds("Updated 2 minutes ago") == 120
    assert updated_label_age_seconds("") is None
    assert label_is_recent("Updated 8 minutes ago", recent_seconds=600)
    assert not label_is_recent("Updated 15 hours ago", recent_seconds=600)


def test_refresh_skips_click_when_label_is_already_recent() -> None:
    page = FakePage(["Updated a few seconds ago"])
    clock = _Clock()
    observed = refresh_rates_page(
        page,  # type: ignore[arg-type]
        channel="Booking.com",
        now=lambda: OBSERVED_AT,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )
    assert page.clicks == 0
    assert observed.clicked is False
    assert observed.refresh_label == "Updated a few seconds ago"
    assert observed.refreshed_at == OBSERVED_AT.isoformat()


def test_refresh_clicks_once_and_retries_poll_without_clicking_again() -> None:
    page = FakePage(
        [
            "Updated 15 hours ago",
            "Updated 15 hours ago",
            "Updated a few seconds ago",
        ],
            fail_on={2},
    )
    clock = _Clock()
    observed = refresh_rates_page(
        page,  # type: ignore[arg-type]
        channel="Expedia",
        timeout_seconds=1200,
        poll_seconds=15,
        recent_seconds=600,
        now=lambda: OBSERVED_AT,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )
    assert page.clicks == 1
    assert observed.clicked is True
    assert observed.refresh_label == "Updated a few seconds ago"
    assert observed.refreshed_at == OBSERVED_AT.isoformat()
    assert clock.t == 30


def test_refresh_timeout_does_not_click_again() -> None:
    page = FakePage(["Updated 15 hours ago"])
    clock = _Clock()
    with pytest.raises(RatesRefreshTimeout):
        refresh_rates_page(
            page,  # type: ignore[arg-type]
            channel="Brand.com",
            timeout_seconds=30,
            poll_seconds=15,
            now=lambda: OBSERVED_AT,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
    assert page.clicks == 1
