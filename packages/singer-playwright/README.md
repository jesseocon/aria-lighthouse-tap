# singer-playwright

Shared Playwright + Singer SDK primitives for browser-backed taps.

- `PlaywrightTap` — one Chromium per run, storage_state loading, session probe
- `PlaywrightStream` — extraction-only streams with lazy-load helpers
- `python -m singer_playwright auth` — interactive login → storage_state.json
- `python -m singer_playwright workshop` — AI-forward scraper iteration daemon

## Workshop (scraper development loop)

Persistent browser session for observe → act → extract → recipe → codegen:

```bash
# Start daemon (background)
uv run python -m singer_playwright workshop start --storage-state storage_state.json --detach

# Observe current page
uv run python -m singer_playwright workshop observe

# Navigate and extract
uv run python -m singer_playwright workshop goto --url 'https://example.com'
uv run python -m singer_playwright workshop extract --selector 'table.data'

# Save and replay recipe
uv run python -m singer_playwright workshop recipe save --brief briefs/strategy-snapshot.yaml --records '[]'
uv run python -m singer_playwright workshop recipe replay --recipe workshop-runs/<id>/recipe.json --storage-state storage_state.json

# Generate stream scaffolding
uv run python -m singer_playwright workshop codegen --recipe workshop-runs/<id>/recipe.json --output-dir packages/tap-lighthouse/tap_lighthouse

# Stop
uv run python -m singer_playwright workshop stop
```

See `.cursor/skills/playwright-scraper-workshop/SKILL.md` for the agent protocol.
