"""Day-by-day navigation retries."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tap_lighthouse.navigation import DayByDayUrlOptions, navigate_to_day_by_day


def test_navigate_refreshes_page_after_table_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    page = MagicMock()
    frame = MagicMock()
    ready_calls = {"n": 0}

    def fail_once(_frame: object) -> None:
        ready_calls["n"] += 1
        if ready_calls["n"] == 1:
            raise TimeoutError("Timed out waiting for Spider table data to finish loading")

    monkeypatch.setattr("tap_lighthouse.navigation.get_spider_frame", lambda _page, **_kwargs: frame)
    monkeypatch.setattr("tap_lighthouse.navigation.apply_spider_query_params", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("tap_lighthouse.navigation.wait_for_day_by_day_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("tap_lighthouse.navigation.wait_for_table_ready", fail_once)

    result = navigate_to_day_by_day(
        page,
        "202158",
        options=DayByDayUrlOptions(
            start_date="2025-01-17",
            end_date="2026-01-16",
            as_of_date="2025-01-17",
        ),
    )

    assert result is frame
    assert page.goto.call_count == 2
    assert ready_calls["n"] == 2


def test_navigate_raises_after_refresh_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    page = MagicMock()

    def still_loading(_frame: object) -> None:
        raise TimeoutError("still loading")

    monkeypatch.setattr("tap_lighthouse.navigation.get_spider_frame", lambda _page, **_kwargs: MagicMock())
    monkeypatch.setattr("tap_lighthouse.navigation.apply_spider_query_params", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("tap_lighthouse.navigation.wait_for_day_by_day_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("tap_lighthouse.navigation.wait_for_table_ready", still_loading)

    with pytest.raises(TimeoutError, match="still loading"):
        navigate_to_day_by_day(page, "202158", attempts=2)

    assert page.goto.call_count == 2
