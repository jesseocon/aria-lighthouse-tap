# Lighthouse Meltano project

## Goal

Replace ad-hoc scrapers with declarative, stateful, schedulable Singer taps for JavaScript-heavy sites (infinite scroll / SPA), some requiring login and occasional 2FA.

This repo is **Lighthouse only** (tap + dbt + warehouse scripts). Shared framework: sibling **`aria-singer-playwright`**.

## Stack

Meltano (orchestration + state) → Singer SDK (tap structure) → Playwright for Python (rendering) via **`singer-playwright`**.

## Granularity

- **One tap = one source (one website).** Owns browser setup, auth artifact path, base URL, rate-limiting.
- **One stream = one entity** within that source (listing, detail page, category index).
- **Other websites → separate git repos** (ProfitSword, CoStar, …), each depending on `aria-singer-playwright` only—not this repo.

## Authentication

Decouple auth from extraction:

1. **Auth** — occasional manual step. Log in interactively, clear 2FA, save Playwright `storage_state.json`. That file is the credential.
2. **Extraction** — automated Meltano run. Tap loads `storage_state.json` and drives Playwright as an already-authenticated user. Never touches login/2FA.

```bash
uv run python -m singer_playwright auth --url https://example.com/login --out storage_state.json
```

Guardrails:

- `storage_state.json` is a bearer credential: out of git, Meltano env/config, locked file perms.
- Tap probes session validity first; if bounced to login, fail with **re-auth needed**.
- Short-lived 2FA sites run on-demand after manual re-auth, not on a hands-off schedule.

## Per-run mechanics

- Launch Chromium **once per run**; reuse context across records.
- Handle lazy load per stream: `wait_for_selector`, scroll, network idle.
- Use Singer replication keys + STATE for incremental runs.
- `playwright install chromium` in Docker for scheduled runs.

## Repo layout

```
packages/tap-lighthouse/   # Lighthouse tap
briefs/                    # Workshop briefs for Lighthouse streams
config/properties/         # Aria property registry + bronze naming
transform/                 # dbt models
```

New vendor sites: scaffold from **`aria-singer-playwright`** (`cookiecutter-vendor-meltano` or `scripts/new-vendor-repo.sh`).

## Build order (Lighthouse)

1. Framework in `aria-singer-playwright` (`PlaywrightTap`, `PlaywrightStream`)
2. Streams in `tap-lighthouse` (strategy-snapshot, parity-list, budget, forecast, …)
3. Incremental STATE + Meltano + BigQuery/dbt in **this** repo only
