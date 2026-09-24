"""Lighthouse workshop page_scripts.js is present for scraper CLI."""

from __future__ import annotations

from pathlib import Path


def test_lighthouse_workshop_page_scripts_exists() -> None:
    path = Path(__file__).resolve().parents[1] / "workshop" / "page_scripts.js"
    assert path.is_file(), "workshop/page_scripts.js required for workshop observe/extract"
    text = path.read_text(encoding="utf-8")
    assert "extractTableScript" in text
    assert ".prism-table table" in text
