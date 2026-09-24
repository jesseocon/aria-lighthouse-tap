# Framework dependency

Lighthouse does **not** vendor `singer-playwright` in this repo.

Clone sibling repos:

```text
meltano-taps/
  aria-singer-playwright/
  aria-lighthouse-tap/      # this repo
```

[`pyproject.toml`](../pyproject.toml) pins:

```toml
[tool.uv.sources]
singer-playwright = { path = "../aria-singer-playwright", editable = true }
```

For CI/Docker without a sibling checkout, switch to a git tag:

```toml
singer-playwright = { git = "https://github.com/jesseocon/aria-singer-playwright.git", rev = "v0.1.0" }
```

New vendor sites: see `aria-singer-playwright/docs/new-vendor-repo.md`.
