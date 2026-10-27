"""Lighthouse runs end their session (or hand it on in a login chain), and prove it."""

from __future__ import annotations

import logging

import pytest

from tap_lighthouse import signout
from tap_lighthouse.tap import TapLighthouse

HOME = "https://app.mylighthouse.com/hotel/280492/overview?compsetId=1"
LOGIN = "https://app.mylighthouse.com/login?next=%2F"


class Item:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    @property
    def first(self) -> Item:
        return self

    def is_visible(self) -> bool:
        return self.page.menu_open

    def wait_for(self, *, state: str, timeout: int) -> None:  # noqa: ARG002
        if not self.page.menu_open:
            raise TimeoutError("menu not open")

    def click(self, **_kw) -> None:
        if not self.page.menu_open:  # Playwright times out clicking a hidden element
            raise TimeoutError("Log out is not visible")
        self.page.clicks.append("Log out")
        self.page.live = self.page.sticky
        self.page.url = LOGIN


class Buttons:
    """The header's icon-only buttons: [settings gear, avatar]."""

    def __init__(self, page: FakePage) -> None:
        self.page = page

    def count(self) -> int:
        return 2

    @property
    def first(self) -> Buttons:
        return self

    def wait_for(self, *, state: str, timeout: int) -> None:  # noqa: ARG002
        self.page.waited_for_header = True

    def nth(self, index: int) -> Buttons:
        self.index = index
        return self

    def click(self, **_kw) -> None:
        self.page.clicks.append("avatar" if self.index == 1 else "gear")
        self.page.menu_open = self.index == 1 and self.page.live


class Keyboard:
    def press(self, _key: str) -> None:
        return None


class FakePage:
    def __init__(self, url: str = HOME, *, live: bool = True, sticky: bool = False) -> None:
        self.url = url
        self.live = live
        self.sticky = sticky
        self.menu_open = False
        self.clicks: list[str] = []
        self.keyboard = Keyboard()
        self.waited_for_header = False

    def locator(self, selector: str):  # noqa: ANN201
        return Item(self) if selector == signout.LOG_OUT_ITEM else Buttons(self)

    def goto(self, url: str, **_kw) -> None:
        self.url = url if self.live else LOGIN

    def wait_for_url(self, predicate, **_kw) -> None:  # noqa: ANN001
        if not predicate(self.url):
            raise TimeoutError(self.url)


def test_log_out_through_the_avatar_menu_and_confirm() -> None:
    page = FakePage()
    assert signout.sign_out(page) == "avatar menu > Log out; confirmed: the app asks for login"
    assert page.clicks == ["avatar", "Log out"] and not page.live
    assert page.waited_for_header  # waits for the app's header before clicking


def test_a_session_lighthouse_already_ended_is_reported_not_failed() -> None:
    page = FakePage(live=False)
    page.url = HOME
    assert signout.sign_out(page).startswith("Lighthouse session had already ended")


def test_still_signed_in_after_log_out_fails_loudly() -> None:
    with pytest.raises(signout.SignOutFailed, match="still opened"):
        signout.sign_out(FakePage(sticky=True))


class Context:
    def storage_state(self, *, path: str) -> None:
        open(path, "w").write('{"cookies": [], "origins": []}')


class Runtime:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.context = Context()
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _tap(page: FakePage, **config) -> tuple[TapLighthouse, Runtime]:
    tap = TapLighthouse(config={"hotel_id": "280492", "auth_method": "password", **config}, validate_config=False)
    runtime = Runtime(page)
    tap._browser_runtime = runtime  # noqa: SLF001
    tap._session_verified = True  # noqa: SLF001
    return tap, runtime


def test_a_password_run_logs_out_at_the_end(caplog) -> None:
    page = FakePage()
    tap, runtime = _tap(page)
    with caplog.at_level(logging.INFO):
        tap.teardown()
    assert not page.live and runtime.stopped
    assert "Signed out of Lighthouse (avatar menu > Log out; confirmed" in caplog.text


def test_in_a_login_chain_the_session_is_handed_on_not_logged_out(tmp_path, caplog) -> None:
    page = FakePage()
    handoff = tmp_path / "storage_state.json"
    tap, runtime = _tap(page, handoff_path=str(handoff))
    with caplog.at_level(logging.INFO):
        tap.teardown()
    assert page.live and page.clicks == [] and handoff.is_file()
    assert "Handed the Lighthouse session to the next run" in caplog.text and runtime.stopped


def test_a_console_saved_session_is_never_logged_out() -> None:
    page = FakePage()
    tap, runtime = _tap(page, auth_method="storage_state")
    tap.teardown()
    assert page.live and page.clicks == [] and runtime.stopped
