"""Provenance helpers for parity-list sync parameters."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

READ_FILTER_STATE_JS = """
() => {
  const normalize = (v) => (v ?? "").replace(/\\s+/g, " ").trim();
  const body = normalize(document.body?.innerText ?? "");
  const memberRate = !!document.querySelector('input[type="checkbox"]');
  const pick = (pattern) => {
    const m = body.match(pattern);
    return m ? m[0] : null;
  };
  return {
    member_rate_toggle_present: memberRate,
    rate_type: pick(/\\bLowest\\b/i),
    device: pick(/\\bDesktop\\b|\\bMobile\\b/i),
    los_label: pick(/\\b\\d+ night\\b/i),
    guests_label: pick(/\\b\\d+ guests?\\b/i),
    room: pick(/\\bAny room\\b/i) || pick(/\\b\\w[\\w\\s-]{0,30} room\\b/i),
    meal: pick(/\\bAny meal\\b/i),
    pos: pick(/\\bDefault POS\\b/i),
    page_url: location.href,
  };
}
"""


def hash_sync_params(params: dict[str, Any]) -> str:
    payload = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def read_page_filter_state(page: Page) -> dict[str, Any]:
    try:
        result = page.evaluate(READ_FILTER_STATE_JS)
        if isinstance(result, dict):
            return result
    except Exception:  # noqa: BLE001
        pass
    return {}


def build_sync_params(
    *,
    hotel_id: str,
    month: str,
    los: int,
    max_persons: int,
    url: str,
    page: Page | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "hotel_id": str(hotel_id),
        "month": month,
        "los": int(los),
        "max_persons": int(max_persons),
        "url": url,
    }
    if page is not None:
        params.update(read_page_filter_state(page))
    if overrides:
        params.update(overrides)
    return dict(sorted(params.items()))
