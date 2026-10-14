"""Type a Lighthouse username and password into the login form."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

PASSWORD_SELECTOR = 'input[type="password"]'
USERNAME_SELECTOR = 'input[type="email"], input[name="username"], input[autocomplete="username"]'
VERIFY_TEXT = "text=/verify it.?s you/i"
EXISTING_SESSION_TEXT = (
    "text=/already signed in|already logged in|another session|signed in elsewhere/i"
)
END_SESSION_BUTTON = (
    'button:has-text("Log out"), button:has-text("Log Out"), '
    'button:has-text("Sign out"), button:has-text("End session")'
)


class LoginRejected(RuntimeError):
    """The site left the password form up after credentials were submitted."""


def apply_credentials(
    page: Page,
    *,
    username: str,
    password: str,
    login_url: str,
    timeout_ms: int = 30_000,
) -> None:
    """Open login_url and submit the credentials in this browser.

    A normal login does not log out. If the page says this account already has
    a session, end that session once and sign in again.
    """
    page.goto(login_url, wait_until="domcontentloaded")
    _sign_in(page, username, password, timeout_ms)
    if _is_existing_session(page):
        _end_existing_session(page)
        page.goto(login_url, wait_until="domcontentloaded")
        _sign_in(page, username, password, timeout_ms)
    if _is_existing_session(page):
        raise LoginRejected("Account already has an active session.")
    if _is_visible(page, PASSWORD_SELECTOR):
        raise LoginRejected("Site rejected the password.")


def _sign_in(page: Page, username: str, password: str, timeout_ms: int) -> None:
    _wait_for_login_form(page, timeout_ms)
    _fill_and_submit(page, username, password, timeout_ms)
    _wait_for_login_result(page, timeout_ms)
    if _is_verify_prompt(page):
        _fill_password(page, password, timeout_ms)
        _click_submit(page)
        _wait_for_login_result(page, timeout_ms)


def _wait_for_login_form(page: Page, timeout_ms: int) -> None:
    page.locator(f"{PASSWORD_SELECTOR}, input[type='email']").first.wait_for(
        state="visible",
        timeout=timeout_ms,
    )


def _fill_and_submit(page: Page, username: str, password: str, timeout_ms: int) -> None:
    if not _is_visible(page, PASSWORD_SELECTOR):
        email = page.locator(USERNAME_SELECTOR).first
        email.wait_for(state="visible", timeout=timeout_ms)
        email.fill(username)
        _click_submit(page)
        _wait_for_password(page, timeout_ms)
    # The email box stays on screen after Sign in. Filling it again sends the
    # form back to the email step and removes the password box.
    _fill_password(page, password, timeout_ms)
    _click_submit(page)


def _wait_for_password(page: Page, timeout_ms: int) -> None:
    password = page.locator(PASSWORD_SELECTOR).first
    try:
        password.wait_for(state="visible", timeout=timeout_ms)
    except Exception as exc:
        raise LoginRejected(_password_missing(page)) from exc


def _password_missing(page: Page) -> str:
    text = ""
    try:
        text = " ".join(page.locator("body").inner_text().split())[:300]
    except Exception:
        text = page.url
    return f"Lighthouse did not show a password field after the email. Page said: {text}"


def _fill_password(page: Page, password: str, timeout_ms: int) -> None:
    page.locator(PASSWORD_SELECTOR).first.fill(password, timeout=timeout_ms)


def _click_submit(page: Page) -> None:
    button = page.locator(
        'button.prism-button--primary:has-text("Sign in"), '
        'button:has-text("Log In"), button:has-text("Log in"), '
        'button:has-text("Sign in"), button:has-text("Continue"), '
        'input[type="submit"]',
    ).first
    button.click()


def _wait_for_login_result(page: Page, timeout_ms: int) -> None:
    page.wait_for_function(
        """() => {
          const text = (document.body && document.body.innerText || '').toLowerCase();
          const verify = text.includes("verify it's you") || text.includes("verify it’s you");
          const pwd = document.querySelector('input[type="password"]');
          const style = pwd ? getComputedStyle(pwd) : null;
          const pwdVisible = !!(pwd && style && style.visibility !== 'hidden' && style.display !== 'none');
          return verify || !pwdVisible;
        }""",
        timeout=timeout_ms,
    )


def _is_existing_session(page: Page) -> bool:
    return _is_visible(page, EXISTING_SESSION_TEXT)


def _end_existing_session(page: Page) -> None:
    if not _is_visible(page, END_SESSION_BUTTON):
        raise LoginRejected("Account already has an active session.")
    page.locator(END_SESSION_BUTTON).first.click()


def _is_verify_prompt(page: Page) -> bool:
    locator = page.locator(VERIFY_TEXT)
    return locator.count() > 0 and locator.first.is_visible()


def _is_visible(page: Page, selector: str) -> bool:
    locator = page.locator(selector)
    return locator.count() > 0 and locator.first.is_visible()
