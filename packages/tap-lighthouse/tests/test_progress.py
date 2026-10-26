"""Progress lines stay greppable and name the step that stopped."""

from __future__ import annotations

import logging

import pytest

from tap_lighthouse.progress import progress


def test_progress_logs_start_and_done(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test_progress")
    with caplog.at_level(logging.INFO, logger="test_progress"):
        with progress(logger, "strategy-snapshot", 2, 5, as_of="2026-09-30") as fields:
            fields["rows"] = 365

    start, done, event = (record.message for record in caplog.records)
    assert start == "PROGRESS stream=strategy-snapshot step=2/5 phase=start as_of=2026-09-30"
    assert done.startswith("PROGRESS stream=strategy-snapshot step=2/5 phase=done elapsed=")
    assert "rows=365" in done and "as_of=2026-09-30" in done
    # The finished step also goes to aria-runner's run log as a progress event.
    assert event == (
        'ARIA {"done":2,"kind":"stream.progress","stream":"strategy-snapshot","total":5,"unit":"steps","v":1}'
    )


def test_progress_logs_failure_and_reraises(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test_progress_fail")
    with caplog.at_level(logging.INFO, logger="test_progress_fail"), pytest.raises(RuntimeError):
        with progress(logger, "rates", 1, 8, channel="Booking.com"):
            raise RuntimeError("page hung")

    assert caplog.records[-1].message.startswith(
        "PROGRESS stream=rates step=1/8 phase=failed elapsed="
    )
    assert "channel=Booking.com" in caplog.records[-1].message
