"""entryId URL parsing tests."""

from __future__ import annotations

from tap_lighthouse.entry_id import parse_entry_id_from_url


def test_parse_entry_id_from_url() -> None:
    assert parse_entry_id_from_url(
        "https://app.mylighthouse.com/hotel/202158/forecast?entryId=21214",
    ) == "21214"
    assert parse_entry_id_from_url(
        "https://app.mylighthouse.com/hotel/202158/forecast?startDate=2026-08-01&entryId=21214",
    ) == "21214"
    assert parse_entry_id_from_url("https://app.mylighthouse.com/hotel/202158/forecast") is None
