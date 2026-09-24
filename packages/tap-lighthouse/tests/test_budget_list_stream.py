"""Budget stream tests with mocked Playwright."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tap_lighthouse.streams import BudgetStream
from tap_lighthouse.tap import TapLighthouse


@patch("tap_lighthouse.streams.resolve_budget_months", return_value=["2026-08", "2026-09", "2026-11"])
@patch("tap_lighthouse.streams.enrich_budget_records")
@patch("tap_lighthouse.streams.extract_budget_rows")
@patch("tap_lighthouse.streams.navigate_to_budget")
@patch("tap_lighthouse.streams.build_budget_sync_params")
@patch("tap_lighthouse.streams.hash_budget_sync_params")
@patch("tap_lighthouse.streams.new_budget_run_metadata")
def test_budget_yields_records_with_provenance(
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
    mock_run_meta.return_value = ("run-budget", "2026-09-17T12:00:00+00:00")
    mock_navigate.return_value = "https://example.com/budget"
    mock_build_params.return_value = {"month": "2026-09", "entry_id": "19564"}
    mock_hash.return_value = "budget-params-hash"
    mock_extract.return_value = ([], [{"date_label": "Tue 01/09/2026"}])
    mock_enrich.return_value = [
        {
            "record_hash": "abc",
            "run_id": "run-budget",
            "run_timestamp": "2026-09-17T12:00:00+00:00",
            "sync_params": "{}",
            "sync_params_hash": "budget-params-hash",
            "stay_date": "2026-09-01",
            "budget_rms_value": "154",
        },
    ]

    tap = TapLighthouse(
        config={
            "storage_state_path": str(state_file),
            "hotel_id": "202158",
            "budget_start_month": "2026-08",
            "budget_forward_months": 2,
        },
    )
    stream = BudgetStream(tap)
    records = list(stream.extract_lighthouse_records(page, None))

    assert mock_navigate.call_count == 3
    assert [call.kwargs["month"] for call in mock_navigate.call_args_list] == [
        "2026-08",
        "2026-09",
        "2026-11",
    ]
    assert len(records) == 3
    assert records[0]["run_id"] == "run-budget"
    assert records[0]["run_timestamp"] == "2026-09-17T12:00:00+00:00"
    assert records[0]["sync_params_hash"] == "budget-params-hash"
    assert records[0]["budget_rms_value"] == "154"
