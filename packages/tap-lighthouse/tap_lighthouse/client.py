"""Lighthouse stream base class."""

from __future__ import annotations

import sys
from abc import abstractmethod
from typing import TYPE_CHECKING

from singer_playwright.session import assert_authenticated
from singer_playwright.stream import PlaywrightStream

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable

    from playwright.sync_api import Frame, Page
    from singer_sdk.helpers.types import Context

    from tap_lighthouse.tap import TapLighthouse


class LighthouseStream(PlaywrightStream):
    """Shared Lighthouse day-by-day navigation and session checks."""

    @property
    def lighthouse_tap(self) -> TapLighthouse:
        from tap_lighthouse.tap import TapLighthouse

        tap = self.playwright_tap
        if not isinstance(tap, TapLighthouse):
            msg = f"{type(self).__name__} requires TapLighthouse"
            raise TypeError(msg)
        return tap

    @property
    def hotel_id(self) -> str:
        return str(self.lighthouse_tap.config["hotel_id"])

    @override
    def extract_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        assert_authenticated(page)
        yield from self.extract_lighthouse_records(page, context)

    @abstractmethod
    def extract_lighthouse_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        """Site-specific extraction implemented by each stream."""

    def navigate_strategy_frame(
        self,
        page: Page,
        *,
        start_date: str,
        end_date: str,
        as_of_date: str,
    ) -> Frame:
        from tap_lighthouse.navigation import DayByDayUrlOptions, navigate_to_day_by_day

        self.polite_sleep()
        return navigate_to_day_by_day(
            page,
            self.hotel_id,
            view="strategy",
            options=DayByDayUrlOptions(
                start_date=start_date,
                end_date=end_date,
                as_of_date=as_of_date,
                pickup_from_date=as_of_date,
            ),
        )
