"""Forecast table extraction for Lighthouse."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tap_lighthouse.monthly_table_export import (
    build_sync_params as _build_sync_params,
    enrich_monthly_records,
    extract_monthly_table_rows,
    hash_sync_params,
    new_run_metadata,
    wait_for_monthly_table,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page

FORECAST_TABLE_SELECTOR = ".prism-table table"

__all__ = [
    "FORECAST_TABLE_SELECTOR",
    "build_sync_params",
    "enrich_forecast_records",
    "extract_forecast_rows",
    "hash_sync_params",
    "new_run_metadata",
    "wait_for_forecast_table",
]


def wait_for_forecast_table(page: Page, *, timeout_ms: int = 60_000) -> None:
    wait_for_monthly_table(page, selector=FORECAST_TABLE_SELECTOR, timeout_ms=timeout_ms)


def extract_forecast_rows(page: Page) -> tuple[list[str], list[dict[str, Any]]]:
    return extract_monthly_table_rows(page, selector=FORECAST_TABLE_SELECTOR)


def build_sync_params(
    *,
    hotel_id: str,
    entry_id: str,
    month: str,
    url: str,
    entry_id_source: str = "redirect",
) -> dict[str, Any]:
    return _build_sync_params(
        hotel_id=hotel_id,
        entry_id=entry_id,
        month=month,
        url=url,
        stream="forecast",
        entry_id_source=entry_id_source,
    )


def enrich_forecast_records(
    rows: list[dict[str, Any]],
    **kwargs: Any,
) -> list[dict[str, Any]]:
    return enrich_monthly_records(rows, **kwargs)
