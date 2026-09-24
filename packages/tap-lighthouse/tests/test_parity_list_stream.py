"""Parity list stream tests with mocked Playwright."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tap_lighthouse.streams import ParityListStream
from tap_lighthouse.tap import TapLighthouse


@patch("tap_lighthouse.parity_months.current_month", return_value="2026-09")
@patch("tap_lighthouse.streams.enrich_parity_records")
@patch("tap_lighthouse.streams.extract_parity_rows_with_hovers")
@patch("tap_lighthouse.streams.navigate_to_parity_list")
@patch("tap_lighthouse.streams.build_sync_params")
@patch("tap_lighthouse.streams.hash_sync_params")
@patch("tap_lighthouse.streams.new_run_metadata")
@patch("singer_playwright.tap.BrowserRuntime")
def test_parity_list_yields_records_with_provenance(
    mock_runtime_cls: MagicMock,
    mock_run_meta: MagicMock,
    mock_hash: MagicMock,
    mock_build_params: MagicMock,
    mock_navigate: MagicMock,
    mock_extract: MagicMock,
    mock_enrich: MagicMock,
    _mock_current_month: MagicMock,
    tmp_path: object,
) -> None:
    state_file = tmp_path / "storage_state.json"  # type: ignore[operator]
    state_file.write_text('{"cookies": [], "origins": []}', encoding="utf-8")

    page = MagicMock()
    runtime = MagicMock()
    runtime.page = page
    mock_runtime_cls.return_value = runtime

    mock_run_meta.return_value = ("run-abc", "2026-09-17T12:00:00+00:00")
    mock_navigate.return_value = "https://example.com/parity"
    mock_build_params.return_value = {"month": "2026-09", "los": 1}
    mock_hash.return_value = "params-hash"
    mock_extract.return_value = ([], [{"date_label": "Thu 17/09", "brand_com": "179"}])
    mock_enrich.return_value = [
        {
            "record_hash": "abc",
            "run_id": "run-abc",
            "run_timestamp": "2026-09-17T12:00:00+00:00",
            "sync_params": "{}",
            "sync_params_hash": "params-hash",
            "stay_date": "2026-09-17",
        },
    ]

    tap = TapLighthouse(
        config={
            "storage_state_path": str(state_file),
            "hotel_id": "202158",
            "parity_forward_months": 2,
        },
    )
    stream = ParityListStream(tap)
    records = list(stream.extract_lighthouse_records(page, None))

    assert mock_navigate.call_count == 3
    assert [call.kwargs["month"] for call in mock_navigate.call_args_list] == [
        "2026-09",
        "2026-10",
        "2026-11",
    ]
    assert len(records) == 3
    assert records[0]["run_id"] == "run-abc"
    assert records[0]["run_timestamp"] == "2026-09-17T12:00:00+00:00"
    assert records[0]["sync_params_hash"] == "params-hash"
