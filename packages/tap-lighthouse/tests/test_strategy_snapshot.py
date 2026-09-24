"""Strategy snapshot stream tests with mocked Playwright."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tap_lighthouse.streams import StrategySnapshotStream
from tap_lighthouse.tap import TapLighthouse


@patch("tap_lighthouse.streams.extract_table_records")
@patch.object(StrategySnapshotStream, "navigate_strategy_frame")
@patch("singer_playwright.tap.BrowserRuntime")
def test_strategy_snapshot_yields_records(
    mock_runtime_cls: MagicMock,
    mock_navigate: MagicMock,
    mock_extract: MagicMock,
    tmp_path: object,
) -> None:
    state_file = tmp_path / "storage_state.json"  # type: ignore[operator]
    state_file.write_text('{"cookies": [], "origins": []}', encoding="utf-8")

    page = MagicMock()
    frame = MagicMock()
    frame.page = page
    mock_navigate.return_value = frame
    mock_extract.return_value = [
        {
            "as_of_date_date": "1/2/25 Thu",
            "on_the_books_ooo_rms_available": "2/181",
            "_hotel_id": "202158",
        },
    ]

    runtime = MagicMock()
    runtime.page = page
    mock_runtime_cls.return_value = runtime

    tap = TapLighthouse(
        config={
            "storage_state_path": str(state_file),
            "hotel_id": "202158",
                "start_date": "2026-09-16",
                "end_date": "2026-09-16",
                "lookback_days": 1,
        },
    )
    stream = StrategySnapshotStream(tap)
    stream.get_starting_replication_key_value = MagicMock(return_value=None)  # type: ignore[method-assign]

    records = list(stream.extract_lighthouse_records(page, None))

    assert stream.primary_keys == ("as_of_date", "stay_date")
    assert len(records) == 1
    assert records[0]["as_of_date"] == "2026-09-16"
    assert records[0]["stay_date"] == "2025-01-02"
    assert records[0]["as_of_date_date"] == "1/2/25 Thu"
    assert records[0]["on_the_books_ooo_rms_available"] == "2/181"
    assert records[0]["record_hash"]
