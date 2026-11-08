"""The password browser records a video when the run asks, and applies stealth only when turned on."""

import json
import logging

import pytest
from playwright.sync_api import Route, sync_playwright

from singer_playwright import browser as browser_module
from singer_playwright import videos
from singer_playwright.progress import MARKER
from tap_lighthouse import tap as tap_module
from tap_lighthouse.tap import _PasswordBrowser


def _answer(route: Route) -> None:
    route.fulfill(status=200, content_type="text/html", body="<h1>Lighthouse</h1>")


def test_a_run_that_asks_for_video_keeps_one_when_the_browser_stops(tmp_path, monkeypatch, caplog) -> None:
    shots = tmp_path / "shots"
    shots.mkdir()
    monkeypatch.setenv("ARIA_SCREENSHOT_DIR", str(shots))
    monkeypatch.setenv("ARIA_RECORD_VIDEO", "1")
    video_dir = videos.recording_dir()
    assert video_dir is not None
    logger = logging.getLogger("test-lighthouse-video")
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch()
    context = browser.new_context(record_video_dir=str(video_dir), record_video_size=videos.SIZE)
    page = context.new_page()
    page.route("https://lighthouse.test/**", _answer)
    page.goto("https://lighthouse.test/")
    page.wait_for_timeout(300)
    with caplog.at_level(logging.INFO, logger="test-lighthouse-video"):
        _PasswordBrowser(playwright, browser, context, page, video_dir=video_dir, logger=logger).stop()

    files = [p.name for p in shots.iterdir()]
    assert len(files) == 1 and files[0].endswith("-browser.webm"), files
    assert not video_dir.exists()
    events = [json.loads(r.getMessage().removeprefix(MARKER)) for r in caplog.records if r.getMessage().startswith(MARKER)]
    assert [(e["code"], e["video"]) for e in events if e["kind"] == "notice"] == [("video", files[0])]


@pytest.mark.parametrize("stealth", [False, True])
def test_stealth_is_applied_only_when_turned_on(stealth, monkeypatch) -> None:
    applied: list[object] = []
    monkeypatch.delenv("ARIA_BROWSER", raising=False)
    monkeypatch.setattr(browser_module, "apply_stealth", applied.append)

    def no_sign_in(page, **_kwargs) -> None:  # noqa: ANN001
        raise RuntimeError("stop before signing in")

    monkeypatch.setattr(tap_module, "apply_credentials", no_sign_in)
    with pytest.raises(RuntimeError):
        _PasswordBrowser.start({"username": "u", "password": "p", "stealth": stealth})
    assert len(applied) == (1 if stealth else 0)


def test_a_failed_sign_in_still_reports_the_browsers_network_bytes(monkeypatch, caplog) -> None:
    monkeypatch.delenv("ARIA_NETWORK_PROFILE", raising=False)

    def sign_in_then_fail(page, **_kwargs) -> None:  # noqa: ANN001
        page.route("https://lighthouse.test/**", _answer)
        page.goto("https://lighthouse.test/login")
        raise RuntimeError("rejected")

    monkeypatch.setattr(tap_module, "apply_credentials", sign_in_then_fail)
    logger = logging.getLogger("test-lighthouse-network")
    with caplog.at_level(logging.INFO, logger="test-lighthouse-network"), pytest.raises(RuntimeError):
        _PasswordBrowser.start({"username": "u", "password": "p"}, logger=logger)
    events = [json.loads(r.getMessage().removeprefix(MARKER)) for r in caplog.records if r.getMessage().startswith(MARKER)]
    [network] = [e for e in events if e["kind"] == "network"]
    assert network["browser"] == "tap (password sign-in)"
    assert network["requests"] >= 1
