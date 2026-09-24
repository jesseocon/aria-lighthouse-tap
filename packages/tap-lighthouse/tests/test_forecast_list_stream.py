"""Forecast stream tests with mocked Playwright."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tap_lighthouse.streams import ForecastStream
from tap_lighthouse.tap import TapLighthouse


@patch("tap_lighthouse.streams.resolve_budget_months", return_value=["2026-09", "2026-11"])
@patch("tap_lighthouse.streams.enrich_forecast_records")
@patch("tap_lighthouse.streams.extract_forecast_rows")
@patch("tap_lighthouse.streams.navigate_to_forecast")
@patch("tap_lighthouse.streams.build_forecast_sync_params")
@patch("tap_lighthouse.streams.hash_forecast_sync_params")
@patch("tap_lighthouse.streams.new_forecast_run_metadata")
@patch("tap_lighthouse.streams.resolve_forecast_entry_id", return_value=("21214", "redirect"))
def test_forecast_yields_records_with_provenance(
    mock_resolve_entry: MagicMock,
    mock_run_meta: MagicMock,
    mock_hash: MagicMock,
    mock_build_params: MagicMock,
    mock_navigate: MagicMock,
    mock_extract: MagicMock,
    mock_enrich: MagicMock,
    _mock_months: MagicMock,
    tmp_path: object,
) -> None:
    state_file = tmp_path / "storage_state.json"  # type: ignore[operator]
    state_file.write_text('{"cookies": [], "origins": []}', encoding="utf-8")

    page = MagicMock()
    mock_run_meta.return_value = ("run-forecast", "2026-09-17T12:00:00+00:00")
    mock_navigate.return_value = "https://example.com/forecast?entryId=21214"
    mock_build_params.return_value = {"month": "2026-09", "entry_id": "21214"}
    mock_hash.return_value = "forecast-params-hash"
    mock_extract.return_value = ([], [{"date_label": "Tue 01/09/2026"}])
    mock_enrich.return_value = [
        {
            "record_hash": "abc",
            "run_id": "run-forecast",
            "run_timestamp": "2026-09-17T12:00:00+00:00",
            "sync_params": '{"entry_id":"21214"}',
            "sync_params_hash": "forecast-params-hash",
            "stay_date": "2026-09-01",
            "user_forecast_rms_value": "0",
        },
    ]

    tap = TapLighthouse(
        config={
            "storage_state_path": str(state_file),
            "hotel_id": "202158",
            "forecast_forward_months": 2,
        },
    )
    stream = ForecastStream(tap)
    records = list(stream.extract_lighthouse_records(page, None))

    mock_resolve_entry.assert_called_once()
    assert mock_navigate.call_count == 2
    assert len(records) == 2
    assert records[0]["run_id"] == "run-forecast"
    assert records[0]["user_forecast_rms_value"] == "0"
