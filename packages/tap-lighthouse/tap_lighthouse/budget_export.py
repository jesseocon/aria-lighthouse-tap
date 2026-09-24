"""Budget table extraction for Lighthouse."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tap_lighthouse.monthly_table_export import (
    build_sync_params as _build_sync_params,
    enrich_monthly_records,
    extract_monthly_table_rows,
    hash_sync_params,
    month_bounds,
    new_run_metadata,
    parse_stay_date,
    wait_for_monthly_table,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page

BUDGET_TABLE_SELECTOR = (
    ".ic-product-tour-48864127-budget-table table, .prism-table table"
)

__all__ = [
    "BUDGET_TABLE_SELECTOR",
    "build_sync_params",
    "enrich_budget_records",
    "extract_budget_rows",
    "hash_sync_params",
    "month_bounds",
    "new_run_metadata",
    "parse_stay_date",
    "wait_for_budget_table",
]


def wait_for_budget_table(page: Page, *, timeout_ms: int = 60_000) -> None:
    wait_for_monthly_table(page, selector=BUDGET_TABLE_SELECTOR, timeout_ms=timeout_ms)


def extract_budget_rows(page: Page) -> tuple[list[str], list[dict[str, Any]]]:
    return extract_monthly_table_rows(page, selector=BUDGET_TABLE_SELECTOR)


def build_sync_params(
    *,
    hotel_id: str,
    entry_id: str,
    month: str,
    variance: str,
    url: str,
) -> dict[str, Any]:
    return _build_sync_params(
        hotel_id=hotel_id,
        entry_id=entry_id,
        month=month,
        url=url,
        stream="budget",
        variance=variance,
    )


def enrich_budget_records(
    rows: list[dict[str, Any]],
    **kwargs: Any,
) -> list[dict[str, Any]]:
    return enrich_monthly_records(rows, **kwargs)
