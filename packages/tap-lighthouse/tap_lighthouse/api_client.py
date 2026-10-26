"""Lighthouse API calls issued from inside the authenticated page.

Requests run through the page's own ``fetch`` so origin, referer, cookies,
user agent, and ``sec-fetch-*`` headers match the app's requests exactly.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from singer_playwright.errors import ReAuthRequiredError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from logging import Logger

    from playwright.sync_api import Frame, Page

# The Lighthouse app's jQuery requests send these; matching them keeps v2 indistinguishable.
APP_REST_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
}

RETRYABLE_STATUSES = frozenset({0, 429, 500, 502, 503, 504})
AUTH_STATUSES = frozenset({401, 403})
DEFAULT_RETRY_DELAYS = (30.0, 120.0)

FETCH_ALL_JS = """
async (requests) => {
  const run = async (r) => {
    try {
      const resp = await fetch(r.url, {
        method: r.method,
        headers: r.headers,
        body: r.body,
        credentials: 'include',
      });
      return {
        status: resp.status,
        url: resp.url,
        redirected: resp.redirected,
        contentType: resp.headers.get('content-type') || '',
        text: await resp.text(),
        error: null,
      };
    } catch (e) {
      return { status: 0, url: r.url, redirected: false, contentType: '', text: '', error: String(e) };
    }
  };
  return Promise.all(requests.map(run));
}
"""


class LighthouseApiError(RuntimeError):
    """An API call failed in a way retrying will not fix."""


@dataclass(frozen=True)
class ApiRequest:
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    label: str = ""
    # Optional enrichment: a 401/403 that is not a login redirect means the hotel is not
    # entitled to it, so the caller gets the response back instead of a re-auth error.
    optional: bool = False

    def to_js(self) -> dict[str, Any]:
        return {"url": self.url, "method": self.method, "headers": self.headers, "body": self.body}


@dataclass(frozen=True)
class ApiResponse:
    request: ApiRequest
    status: int
    url: str
    content_type: str
    text: str
    redirected: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:  # noqa: ANN401
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as exc:
            msg = f"{self.request.label or self.request.url}: response is not JSON ({self.content_type})"
            raise LighthouseApiError(msg) from exc


def is_not_entitled(response: ApiResponse) -> bool:
    """An optional request refused for this hotel, while the session itself is still good."""
    return (
        response.request.optional
        and response.status in AUTH_STATUSES
        and "/login" not in response.url
        and "text/html" not in response.content_type.lower()
    )


def is_login_response(response: ApiResponse) -> bool:
    if response.status in AUTH_STATUSES:
        return True
    if "/login" in response.url:
        return True
    return response.ok and "text/html" in response.content_type.lower()


class ApiClient:
    """Runs batches of requests in a page or frame, with slow retries and no hammering."""

    def __init__(
        self,
        target: Page | Frame,
        *,
        logger: Logger,
        retry_delays: Sequence[float] = DEFAULT_RETRY_DELAYS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.target = target
        self.logger = logger
        self.retry_delays = tuple(retry_delays)
        self._sleep = sleep

    def fetch_all(self, requests: Sequence[ApiRequest]) -> list[ApiResponse]:
        """Send requests concurrently (as the app does for one view) and return them in order."""
        results: list[ApiResponse | None] = [None] * len(requests)
        pending = list(range(len(requests)))
        for attempt in range(len(self.retry_delays) + 1):
            raw = self.target.evaluate(FETCH_ALL_JS, [requests[i].to_js() for i in pending])
            retry: list[int] = []
            for index, item in zip(pending, raw, strict=True):
                response = ApiResponse(
                    request=requests[index],
                    status=int(item.get("status") or 0),
                    url=str(item.get("url") or requests[index].url),
                    content_type=str(item.get("contentType") or ""),
                    text=str(item.get("text") or ""),
                    redirected=bool(item.get("redirected")),
                    error=item.get("error"),
                )
                if is_not_entitled(response):
                    results[index] = response
                    continue
                if is_login_response(response):
                    msg = (
                        f"Lighthouse API {response.request.label or response.request.url} returned "
                        f"{response.status} ({response.url}); the saved session is no longer valid. "
                        "Run auth again, then retry."
                    )
                    raise ReAuthRequiredError(msg)
                results[index] = response
                if response.status in RETRYABLE_STATUSES:
                    retry.append(index)
            if not retry:
                break
            if attempt == len(self.retry_delays):
                failed = results[retry[0]]
                assert failed is not None
                msg = (
                    f"Lighthouse API {failed.request.label} still failing after "
                    f"{attempt + 1} attempts: status={failed.status} error={failed.error}"
                )
                raise LighthouseApiError(msg)
            delay = self.retry_delays[attempt]
            self.logger.warning(
                "Lighthouse API retry in %.0fs: %s",
                delay,
                ", ".join(f"{results[i].request.label}={results[i].status}" for i in retry),  # type: ignore[union-attr]
            )
            self._sleep(delay)
            pending = retry

        final: list[ApiResponse] = []
        for response in results:
            assert response is not None
            if not response.ok and response.request.optional:
                final.append(response)
                continue
            if not response.ok:
                msg = f"Lighthouse API {response.request.label} failed: status={response.status} body={response.text[:300]}"
                raise LighthouseApiError(msg)
            final.append(response)
        return final

    def fetch_json(self, request: ApiRequest) -> Any:  # noqa: ANN401
        return self.fetch_all([request])[0].json()


class Pacer:
    """Random pause between batches, roughly the pace of a person changing a filter."""

    def __init__(
        self,
        min_seconds: float,
        max_seconds: float,
        *,
        sleep: Callable[[float], None] = time.sleep,
        uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if min_seconds < 0 or max_seconds < min_seconds:
            msg = f"Invalid pause range {min_seconds}..{max_seconds}"
            raise ValueError(msg)
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds
        self._sleep = sleep
        self._uniform = uniform
        self._first = True

    def pause(self) -> float:
        """Sleep before every batch except the first; return the seconds slept."""
        if self._first:
            self._first = False
            return 0.0
        seconds = self._uniform(self.min_seconds, self.max_seconds)
        self._sleep(seconds)
        return seconds


def camel_to_snake(name: str) -> str:
    out: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index and (name[index - 1].islower() or name[index - 1].isdigit()):
            out.append("_")
        out.append(char.lower())
    return "".join(out)
