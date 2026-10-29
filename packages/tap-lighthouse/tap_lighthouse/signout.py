"""End the Lighthouse session when a run (or a login chain) finishes.

Observed 2026-10-27 in a workshop session: the avatar button at the top right opens a menu
whose last item is "Log out"; it calls POST /api/v3/logout/ and lands on /login. A signed-out
browser that loads any app page is sent to /login, which is how a sign-out is confirmed.

Lighthouse sometimes ends the session without leaving the page (seen 2026-10-29), so a
sign-out is always confirmed by loading the app again. When the menu cannot be used (a hotel
page drew something over the header) or the session is still open, the run makes the same
logout call the menu makes (recorded 2026-10-26: POST, empty body, the csrftoken cookie as
X-CSRFToken) and confirms again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

APP_HOME = "https://app.mylighthouse.com/"
LOGIN_PATH = "/login"
LOG_OUT_ITEM = "text=/^\\s*Log out\\s*$/ >> visible=true"
LOGOUT_CALL = "https://app.mylighthouse.com/api/v3/logout/"
# The header's icon-only buttons are the settings gear and the avatar; the avatar opens the menu.
# Only visible ones: the app renders after load (a fresh page needs a few seconds).
HEADER_ICON_BUTTONS = "button.prism-button--icon-only:visible"


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
        # The end of a login chain opens a fresh page: wait for the app to draw its header.
        page.locator(HEADER_ICON_BUTTONS).first.wait_for(state="visible", timeout=timeout_ms)
        buttons = page.locator(HEADER_ICON_BUTTONS)
        for index in reversed(range(buttons.count())):  # the avatar is the last one
            buttons.nth(index).click(timeout=timeout_ms)
            try:
                item.wait_for(state="visible", timeout=3_000)
                break
            except Exception:  # noqa: BLE001 - not the avatar; close and try the next
                page.keyboard.press("Escape")
    item.click(timeout=timeout_ms)


def _logout_call(page: Page, timeout_ms: int) -> None:
    """The request the Log out item sends, from this browser's own session."""
    token = next((c["value"] for c in page.context.cookies(APP_HOME) if c["name"] == "csrftoken"), "")
    page.request.post(
        LOGOUT_CALL,
        headers={
            "X-CSRFToken": token,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": page.url or APP_HOME,
        },
        max_redirects=0,
        timeout=timeout_ms,
    )


def _first_line(exc: BaseException) -> str:
    return (str(exc).splitlines() or [type(exc).__name__])[0]


def sign_out(page: Page, *, timeout_ms: int = 30_000) -> str:
    """Log out through the avatar menu (or the call it makes), then prove the session is closed.

    Returns what happened.
    """
    if _on_login(page):
        return "already on the login page; nothing to sign out"
    at = page.url
    try:
        _open_menu_and_log_out(page, timeout_ms)
    except Exception as exc:  # noqa: BLE001 - the logout call below is the fallback
        if session_closed(page, timeout_ms=timeout_ms):
            return "Lighthouse session had already ended; nothing to sign out (confirmed: the app asks for login)"
        menu = f"avatar menu failed from {at}: {_first_line(exc)}"
    else:
        if session_closed(page, timeout_ms=timeout_ms):
            return "avatar menu > Log out; confirmed: the app asks for login"
        menu = f"logged out via the menu, but the app still opened ({page.url})"
    try:
        _logout_call(page, timeout_ms)
    except Exception as exc:  # noqa: BLE001
        raise SignOutFailed(f"{menu}; the logout call failed: {_first_line(exc)}") from exc
    if session_closed(page, timeout_ms=timeout_ms):
        return f"{menu}; the app's logout call; confirmed: the app asks for login"
    raise SignOutFailed(f"{menu}; the logout call did not close the session either")
