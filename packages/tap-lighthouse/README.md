# tap-lighthouse

Self-contained Singer tap for Lighthouse (OTA Insight) Day-by-day exports via Playwright.

The in-browser table exporter ships inside this package at
`tap_lighthouse/vendor/browser-export.js` — no external repo required at runtime.

## Streams

- `strategy-snapshot` — sliding window strategy export; incremental on `as_of_date`; upserts on `as_of_date` + `stay_date`
- `parity-list` — parity table with OTA hover detail; append-only history on `run_timestamp`
- `budget` — monthly budget table; append-only history on `run_timestamp`

### v2 (API) streams

Load the page once, then call the page's own JSON APIs via in-page `fetch` (same cookies, origin, headers). Random 4–9 s pause between batches (`api_pause_min_seconds` / `api_pause_max_seconds`); 429/5xx retried after 30 s, then 120 s; 401/403 or a login redirect stops with re-auth needed. API reference: `docs/lighthouse-api/`.

- `strategy-snapshot-v2` — Spider GraphQL; 7 calls per as-of date; incremental on `as_of_date`. `strategy_v2_pickup_days` (default 7), `strategy_v2_max_as_of_dates` (backfill cap, 0 = none).
- `rates-v2` — one `rates/` call per month × channel × rate type, plus hotels, My OTB, demand, and events once per run. One row per stay date × comp-set hotel. `rates_v2_refresh` (default off) clicks Refresh rates first.
- `parity-list-v2` — one `parities/` call per month; one row per stay date × OTA offer.

### parity-list provenance

Each record includes:

- `run_id`, `run_timestamp` — shared across all rows in a tap run
- `sync_params` — JSON snapshot of page parameters and filter state
- `sync_params_hash` — stable hash of `sync_params`
- `stay_date` — ISO date parsed from the row label
- `record_hash` — surrogate key for the row (`run_id` + `stay_date` + `sync_params_hash`)
- `_parity_entity_labels` — JSON map of channel key → human label (Brand.com, Booking.com, …)

`run_timestamp` is parity-as-of (full timestamp; multiple runs per day are kept).

Parity is forward-looking only. Every sync scrapes the current month plus
`parity_forward_months` (default 2: next month and next+1).

Configure via `parity_los`, `parity_max_persons`, `parity_forward_months`.

### budget provenance

Each record includes:

- `run_id`, `run_timestamp` — shared across all rows in a tap run
- `sync_params` / `sync_params_hash` — page parameters (`entryId`, month window, variance)
- `stay_date` — ISO date parsed from labels like `Tue 01/09/2026`
- `record_hash` — surrogate key (`run_id` + `stay_date` + `sync_params_hash`)

Every sync scrapes `budget_start_month` (default: current month) through current
plus `budget_forward_months` (default 2).

Configure via `budget_variance`, `budget_start_month`,
`budget_forward_months`.

## Config

See root `meltano.yml`. Requires a saved `storage_state.json` from:

```bash
uv run python -m singer_playwright auth \
  --url https://app.mylighthouse.com/login \
  --out storage_state.json
```
