"""Resolve Lighthouse entryId query params from page URLs."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from playwright.sync_api import Page


def parse_entry_id_from_url(url: str) -> str | None:
    params = parse_qs(urlparse(url).query)
    for key in ("entryId", "entryid"):
        values = params.get(key)
        if values and values[0]:
            return str(values[0])
    return None


def resolve_entry_id_from_redirect(
    page: Page,
    *,
    path: str,
    timeout_ms: int = 30_000,
) -> str:
    """Load a bare entity URL and return entryId from the post-redirect location."""
    page.goto(path, wait_until="domcontentloaded")
    deadline = time.time() + (timeout_ms / 1000)
    last_url = page.url
    while time.time() < deadline:
        last_url = page.url
        entry_id = parse_entry_id_from_url(last_url)
        if entry_id:
            return entry_id
        page.wait_for_timeout(500)
    msg = f"Timed out resolving entryId from redirect (last url={last_url})"
    raise TimeoutError(msg)
