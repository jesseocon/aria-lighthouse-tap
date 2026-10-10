"""One log line per unit of work so a run shows where it is and where it stopped."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def progress(
    logger: Any,  # noqa: ANN401 - Singer logger
    stream: str,
    step: int,
    total: int,
    **details: object,
) -> Iterator[dict[str, object]]:
    """Log phase=start immediately, then phase=done or phase=failed with elapsed seconds.

    The yielded dict is included in the closing line, so callers can add rows= there.
    A hang leaves the last line at phase=start for that step.
    """
    fields: dict[str, object] = dict(details)
    started = time.monotonic()
    logger.info("PROGRESS %s", _format(stream, step, total, "start", None, fields))
    try:
        yield fields
    except Exception:
        logger.info(
            "PROGRESS %s",
            _format(stream, step, total, "failed", time.monotonic() - started, fields),
        )
        raise
    else:
        logger.info(
            "PROGRESS %s",
            _format(stream, step, total, "done", time.monotonic() - started, fields),
        )


def _format(
    stream: str,
    step: int,
    total: int,
    phase: str,
    elapsed: float | None,
    fields: dict[str, object],
) -> str:
    parts = [f"stream={stream}", f"step={step}/{total}", f"phase={phase}"]
    if elapsed is not None:
        parts.append(f"elapsed={elapsed:.0f}s")
    parts.extend(f"{key}={value}" for key, value in fields.items())
    return " ".join(parts)
