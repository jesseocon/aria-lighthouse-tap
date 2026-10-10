# aria-lighthouse-tap (Meltano)

## Operations instructions
### Logging in
```bash
uv run python -m singer_playwright auth \
  --url https://app.mylighthouse.com/login \
  --out storage_state.json
```

### Syncing with dates and headed
```bash
TAP_LIGHTHOUSE_HEADLESS=false uv run python -m lighthouse_connector sync hilton-garden-inn-boston-burlington \
  --start-date 2025-09-01 \
  --end-date 2025-09-30
```

Meltano project for **Lighthouse (OTA Insight)**. Framework **`singer-playwright`** is pulled from GitHub (tap + Meltano `pip_url`); optional sibling checkout only for framework hacking — see [docs/framework.md](docs/framework.md).

## Quick start

```bash
git clone https://github.com/jesseocon/aria-lighthouse-tap.git
cd aria-lighthouse-tap

uv sync
uv run meltano install

# Install Playwright Chromium
uv run playwright install chromium

# Save a session (interactive login + 2FA)
uv run python -m singer_playwright auth \
  --url https://app.mylighthouse.com/login \
  --out storage_state.json

# Discover streams
uv run meltano invoke tap-lighthouse --discover

# Sync into hospitalityops-dev and hospitalityops (one Lighthouse scrape)
uv run python -m lighthouse_connector sync hilton-garden-inn-boston-burlington
```

## BigQuery pipeline (`mlt_` prefix)

Tables follow the aria-lighthouse warehouse naming convention with an `mlt_` source prefix so they never collide with the existing CSV/GCS pipeline.

**Bronze is hotel-keyed** (one scrape per Lighthouse `hotel_id`). **Silver and gold are property-keyed.** The Meltano environment picks the BigQuery project and the Aria `property_id` together:

| Environment | BigQuery project | Property id field |
| --- | --- | --- |
| `development` (default) | `hospitalityops-dev` | `development_property_id` |
| `production` | `hospitalityops` | `production_property_id` |

```text
{project}.bronze_{org_id}.mlt_lighthouse_ota__snapshot_daily_hotel_{hotel_id}
{project}.bronze_{org_id}.mlt_lighthouse_ota__parity_list_hotel_{hotel_id}
{project}.silver_{org_id}.mlt_lighthouse_ota__snapshot_daily_{property_id}
{project}.silver_{org_id}.mlt_lighthouse_ota__parity_list_{property_id}
{project}.silver_{org_id}.mlt_lighthouse_ota__parity_metasearch_loss_{property_id}
{project}.gold_{org_id}.mlt_mart__commercial__otb_daily_{property_id}
{project}.gold_{org_id}.mlt_mart__commercial__rate_shop_daily_{property_id}
{project}.gold_{org_id}.mlt_mart__commercial__parity_daily_{property_id}
{project}.gold_{org_id}.mlt_mart__commercial__parity_loss_daily_{property_id}
{project}.gold_{org_id}.mlt_mart__commercial__budget_daily_{property_id}
{project}.gold_{org_id}.mlt_mart__commercial__forecast_daily_{property_id}
```

Run the sync with no `--environment` to scrape Lighthouse once, copy that bronze into production, and build silver/gold in both projects. Pass `--environment` to limit the run to one warehouse.

### Property registry

Property bindings live in [`config/properties/registry.yml`](config/properties/registry.yml). Each row defines:

- `slug` — CLI key for `lighthouse_connector sync` and the runner connection id
- `hotel_id` — Lighthouse natural key (one scrape, shared by both warehouses)
- `development_property_id` / `production_property_id` — Aria property id for that environment

The scrape records the rate-shop group, the comp set, which column is this hotel, and the parity channels.

Org-level `bq_project_development` and `bq_project_production` name the two GCP projects for the CLI. A runner connection omits them and writes to `hospitalityops-dev` and `hospitalityops`. Add rows as you onboard properties.

### Sync one property

```bash
# One Lighthouse scrape → hospitalityops-dev and hospitalityops
uv run python -m lighthouse_connector sync hilton-garden-inn-boston-burlington

# One warehouse only
uv run python -m lighthouse_connector sync hilton-garden-inn-boston-burlington --environment development
uv run python -m lighthouse_connector sync hilton-garden-inn-boston-burlington --environment production

# Transform only (bronze already loaded)
uv run python -m lighthouse_connector sync hilton-garden-inn-boston-burlington --transform-only

# Scrape only
uv run python -m lighthouse_connector sync hilton-garden-inn-boston-burlington --scrape-only
```

### Sync all registered properties

```bash
uv run python -m lighthouse_connector sync --all

# One warehouse only
uv run python -m lighthouse_connector sync --all --environment development

# Backfill a bounded as_of_date range (clears tap bookmarks by default)
uv run python -m lighthouse_connector sync --all --start-date 2025-09-01 --end-date 2025-09-30
```

`--start-date` and `--end-date` bound which snapshot dates (`as_of_date`) are scraped. When both are set, exactly that range is synced. State is cleared by default so bookmarks do not skip dates. Use `--keep-state` only for incremental lookback runs.

One Meltano install under `.meltano/`. Each sync sets `TAP_LIGHTHOUSE_HOTEL_ID` and BigQuery `stream_maps` for that slug as process env vars (`meltano.yml` is never rewritten). The default run scrapes once into `development` and copies bronze into `production`. Bookmarks are per property: state id `{environment}:tap-lighthouse-to-target-bigquery:{slug}`. A date-range backfill starts from empty state unless `--keep-state`. Add `--dry-run` to print the Meltano commands without running them.

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
packages/lighthouse-connector/ # aria-runner connector + local sync CLI
scripts/                     # workshop helpers, lib/ (registry helpers)
transform/                   # dbt silver + gold models
```

**Framework (separate repo):** `../aria-singer-playwright` — `PlaywrightTap`, auth CLI, workshop, vendor cookiecutter.

**Docker (connector image for aria-runner):**

```bash
docker build --build-arg ARIA_RUNNER_IMAGE=aria-runner:latest -t aria-connector-lighthouse .
```

The image entry point is `python -m aria_runner execute --run-id …`: one sync run per Cloud Run Job execution.

## Org sync runner

Scheduled and on-demand runs go through [`aria-runner`](../aria-runner): a control-plane API (connections, schedules, logins, run history in Postgres) and one Cloud Run Job execution per run using this image. Seed connections from the registry:

```bash
uv run python -m lighthouse_connector connections --out connections.json
uv run python -m aria_runner connectors register --installed lighthouse
uv run python -m aria_runner connections put --file connections.json
```

**Git:** [github.com/jesseocon/aria-lighthouse-tap](https://github.com/jesseocon/aria-lighthouse-tap) (distinct from legacy `aria-lighthouse`.)

## Auth model

Authentication is **decoupled** from extraction:

1. Run `python -m singer_playwright auth` once (manual login / 2FA). With the runner, Aria opens a streamed login from `POST /v1/connections/{id}/auth-sessions`, or run `python -m aria_runner login <connection>` locally.
2. Point the tap at `storage_state.json` via Meltano config. Runner jobs download the connection's session from Cloud Storage into a private temp file.
3. Scheduled runs probe the saved session first and stop as `reauth_required` if it expired.

See [CLAUDE.md](./CLAUDE.md) for the full design brief.
