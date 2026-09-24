# Playwright + Singer/Meltano Scraping Framework

## Goal

Replace ad-hoc scrapers with declarative, stateful, schedulable Singer taps for JavaScript-heavy sites (infinite scroll / SPA), some requiring login and occasional 2FA.

## Stack

Meltano (orchestration + state) → Singer SDK (tap structure) → Playwright for Python (rendering).

## Granularity

- **One tap = one source (one website).** Owns browser setup, auth artifact path, base URL, rate-limiting.
- **One stream = one entity** within that source (listing, detail page, category index).
- **Several unrelated sites → one tap per site**, not one universal tap.
- Shared Playwright machinery lives in `packages/singer-playwright` (`PlaywrightTap`, `PlaywrightStream`).

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

## Monorepo layout

```
packages/singer-playwright/   # shared library (not a tap)
packages/tap-<site>/          # one tap per website
cookiecutter-tap-browser/     # scaffold new site taps
```

## Build order

1. `singer-playwright` base classes
2. First site tap (`tap-lighthouse`) with one real stream (`strategy-snapshot`)
3. Incremental STATE
4. Cookiecutter for additional sites
