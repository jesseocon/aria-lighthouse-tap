"""Tests drive fake pages with no mouse or keyboard: humanized input and pacing are off for them."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _plain_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARIA_HUMANIZE", "0")
