# {{ cookiecutter.tap_id }}

Singer tap for **{{ cookiecutter.source_name }}** via Playwright.

## Auth

```bash
uv run python -m singer_playwright auth --url {{ cookiecutter.login_url }} --out storage_state.json
```

## Develop

Add the snippet in `meltano.plugin.yml.snippet` to the root `meltano.yml`, then:

```bash
uv run meltano invoke {{ cookiecutter.tap_id }} --discover
```
