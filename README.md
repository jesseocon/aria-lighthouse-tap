# aria-lighthouse-tap (Meltano)

Meltano project for **Lighthouse (OTA Insight)** only. Shared Playwright + Singer machinery lives in the sibling repo **`../aria-singer-playwright`** (install via `uv sync`). Other vendors get their own repos—see that framework’s `docs/new-vendor-repo.md`.

## Quick start

```bash
# Install workspace deps
uv sync

# Install Playwright Chromium
uv run playwright install chromium

# Save a session (interactive login + 2FA)
uv run python -m singer_playwright auth \
  --url https://app.mylighthouse.com/login \
  --out storage_state.json

# Discover streams
uv run meltano invoke tap-lighthouse --discover

# Local scrape → JSONL (no GCP)
uv run meltano --environment=local run tap-lighthouse target-jsonl
```

## BigQuery pipeline (`mlt_` prefix)

Tables follow the aria-lighthouse warehouse naming convention with an `mlt_` source prefix so they never collide with the existing CSV/GCS pipeline.

**Bronze is hotel-keyed** (one scrape per Lighthouse `hotel_id`). **Silver and gold are property-keyed** (prod + dev Aria `property_id` tiers from the same bronze):

```text
hospitalityops.bronze_{org_id}.mlt_lighthouse_ota__snapshot_daily_hotel_{hotel_id}
hospitalityops.bronze_{org_id}.mlt_lighthouse_ota__parity_list_hotel_{hotel_id}
hospitalityops.silver_{org_id}.mlt_lighthouse_ota__snapshot_daily_{property_id}
hospitalityops.silver_{org_id}.mlt_lighthouse_ota__parity_list_{property_id}
hospitalityops.silver_{org_id}.mlt_lighthouse_ota__parity_metasearch_loss_{property_id}
hospitalityops.gold_{org_id}.mlt_mart_day_by_day_grid_{property_id}
hospitalityops.gold_{org_id}.mlt_mart_rate_shop_daily_{property_id}
hospitalityops.gold_{org_id}.mlt_mart_parity_list_{property_id}
hospitalityops.gold_{org_id}.mlt_mart_parity_metasearch_loss_{property_id}
```

### Property registry

Property bindings live in [`config/properties/registry.yml`](config/properties/registry.yml). Each row defines:

- `slug` — CLI key for sync scripts
- `hotel_id` — Lighthouse natural key (one scrape)
- `prod_property_id` / `dev_property_id` — Aria tiers (two dbt runs per scrape)
- `subject_entity_key`, `pivot_parent_group_slug`, `rate_shop_dimensions`
- `parity_channel_dimensions` — channel keys + labels for parity viz (`_parity_entity_labels`)

Add rows as you onboard properties. No per-property Meltano environment blocks required.

### Sync one property (scrape + both tiers)

```bash
# Full sync: scrape once → dbt prod → dbt dev
./scripts/sync-property.sh hilton-garden-inn-boston-burlington --tier both

# Transform only (bronze already loaded)
./scripts/sync-property.sh hilton-garden-inn-boston-burlington --transform-only --tier prod

# Scrape only
./scripts/sync-property.sh hilton-garden-inn-boston-burlington --scrape-only
```

### Sync all registered properties

```bash
./scripts/sync-all.sh --tier both

# Backfill a bounded as_of_date range (clears tap bookmarks by default)
./scripts/sync-all.sh --tier both --start-date 2025-09-01 --end-date 2025-09-30
```

`--start-date` and `--end-date` bound which snapshot dates (`as_of_date`) are scraped. When both are set, exactly that range is synced. State is cleared by default so bookmarks do not skip dates. Use `--keep-state` only for incremental lookback runs.

One Meltano install under `.meltano/`. Each sync run sets `TAP_LIGHTHOUSE_HOTEL_ID` and BigQuery `stream_maps` from the registry for that slug. Bookmarks are cleared when switching slugs or when backfilling with `--start-date` / `--end-date` (unless `--keep-state`).

Copy `.env.example` → `.env` and set:

- `TARGET_BIGQUERY_CREDENTIALS_PATH` — GCP service account JSON
- `TAP_LIGHTHOUSE_HOTEL_ID` — optional override for ad-hoc runs

Validate dbt without a full sync:

```bash
uv run meltano --environment=development invoke dbt-bigquery:deps
uv run meltano --environment=development invoke dbt-bigquery:compile
```

If you use Application Default Credentials locally, set `DBT_BIGQUERY_AUTH_METHOD=oauth` (service account JSON via `TARGET_BIGQUERY_CREDENTIALS_PATH` also works).

### Migration from property-keyed bronze

If you previously loaded `mlt_lighthouse_ota__snapshot_daily_{property_id}`, re-scrape into `mlt_lighthouse_ota__snapshot_daily_hotel_{hotel_id}` or copy the table once in BigQuery, then drop the old table after validation.

## Scraper workshop (AI iteration loop)

Run from this repo so `workshop/page_scripts.js` (Lighthouse table heuristics) loads automatically:

```bash
chmod +x scripts/scraper.sh scripts/workshop.sh

./scripts/scraper.sh start --storage-state storage_state.json --detach
./scripts/scraper.sh observe
./scripts/scraper.sh goto --url 'https://app.mylighthouse.com/hotel/202158/day-by-day/strategy'
./scripts/scraper.sh extract --frame-url-pattern 'spider\.kriyarevgen\.com' --selector 'table.analytics.day-by-day'
./scripts/scraper.sh recipe-save --brief briefs/strategy-snapshot.yaml --records '[]'
./scripts/scraper.sh codegen --recipe workshop-runs/<run_id>/recipe.json --output-dir packages/tap-lighthouse/tap_lighthouse
./scripts/scraper.sh stop
```

Equivalent: `MELTANO_PROJECT_ROOT=$PWD uv run python -m singer_playwright workshop …`

See `.cursor/skills/playwright-scraper-workshop/SKILL.md` and `briefs/strategy-snapshot.yaml`.

## Layout

```
packages/tap-lighthouse/   # Lighthouse tap only
briefs/                      # Lighthouse scraper briefs (workshop)
config/properties/           # Property registry (registry.yml)
scripts/                     # sync-property.sh, sync-all.sh, lib/
transform/                   # dbt silver + gold models
```

**Framework (separate repo):** `../aria-singer-playwright` — `PlaywrightTap`, auth CLI, workshop, vendor cookiecutter.

**Docker:** build from `meltano-taps/` parent: `docker build -f aria-lighthouse-tap/Dockerfile -t aria-lighthouse-tap .`

**Git:** [github.com/jesseocon/aria-lighthouse-tap](https://github.com/jesseocon/aria-lighthouse-tap) (distinct from legacy `aria-lighthouse`.)

## Auth model

Authentication is **decoupled** from extraction:

1. Run `python -m singer_playwright auth` once (manual login / 2FA).
2. Point the tap at `storage_state.json` via Meltano config.
3. Scheduled runs load the saved session and fail loudly if it expired.

See [CLAUDE.md](./CLAUDE.md) for the full design brief.
