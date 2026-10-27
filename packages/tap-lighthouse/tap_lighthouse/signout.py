"""End the Lighthouse session when a run (or a login chain) finishes.

Observed 2026-10-27 in a workshop session: the avatar button at the top right opens a menu
whose last item is "Log out"; it calls POST /api/v3/logout/ and lands on /login. A signed-out
browser that loads any app page is sent to /login, which is how a sign-out is confirmed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

APP_HOME = "https://app.mylighthouse.com/"
LOGIN_PATH = "/login"
LOG_OUT_ITEM = "text=/^\\s*Log out\\s*$/"
# The header's icon-only buttons are the settings gear and the avatar; the avatar opens the menu.
HEADER_ICON_BUTTONS = "button.prism-button--icon-only"


class SignOutFailed(RuntimeError):
    pass


def _on_login(page: Page) -> bool:
    return LOGIN_PATH in page.url


def session_closed(page: Page, *, timeout_ms: int = 30_000) -> bool:
    """Load the app: a closed session is sent to the login page."""
    try:
        page.goto(APP_HOME, wait_until="load", timeout=timeout_ms)
        page.wait_for_url(lambda url: LOGIN_PATH in url, timeout=timeout_ms)
    except Exception:  # noqa: BLE001 - still in the app means still signed in
        return _on_login(page)
    return True


def _open_menu_and_log_out(page: Page, timeout_ms: int) -> None:
    item = page.locator(LOG_OUT_ITEM).first
    if not item.is_visible():
        buttons = page.locator(HEADER_ICON_BUTTONS)
        for index in reversed(range(buttons.count())):  # the avatar is the last one
            buttons.nth(index).click(timeout=timeout_ms)
            try:
                item.wait_for(state="visible", timeout=3_000)
                break
            except Exception:  # noqa: BLE001 - not the avatar; close and try the next
                page.keyboard.press("Escape")
    item.click(timeout=timeout_ms)
    page.wait_for_url(lambda url: LOGIN_PATH in url, timeout=timeout_ms)


def sign_out(page: Page, *, timeout_ms: int = 30_000) -> str:
    """Log out through the avatar menu, then prove the session is closed. Returns what happened."""
    if _on_login(page):
        return "already on the login page; nothing to sign out"
    at = page.url
    try:
        _open_menu_and_log_out(page, timeout_ms)
    except Exception as exc:
        if session_closed(page, timeout_ms=timeout_ms):
            return "Lighthouse session had already ended; nothing to sign out (confirmed: the app asks for login)"
        msg = f"from {at}: {str(exc).splitlines()[0]}"
        raise SignOutFailed(msg) from exc
    if not session_closed(page, timeout_ms=timeout_ms):
        msg = f"logged out via the menu, but the app still opened ({page.url})"
        raise SignOutFailed(msg)
    return "avatar menu > Log out; confirmed: the app asks for login"
