# Framework dependency

`singer-playwright` is **not** vendored here. Production install resolves it from GitHub.

## Production / Meltano

- Tap declares: `singer-playwright @ git+https://github.com/jesseocon/aria-singer-playwright.git@v0.1.0`
- [`meltano.yml`](../meltano.yml) `pip_url`: git install of this repo’s `packages/tap-lighthouse` (pinned tag).

One clone of [aria-lighthouse-tap](https://github.com/jesseocon/aria-lighthouse-tap) → `uv sync` → `meltano install`.

## Local framework development (optional)

```text
meltano-taps/
  aria-singer-playwright/   # optional sibling
  aria-lighthouse-tap/
```

Root [`pyproject.toml`](../pyproject.toml) overrides with editable path when the sibling exists:

```toml
[tool.uv.sources]
singer-playwright = { path = "../aria-singer-playwright", editable = true }
```

New vendor sites: [aria-singer-playwright/docs/new-vendor-repo.md](https://github.com/jesseocon/aria-singer-playwright/blob/main/docs/new-vendor-repo.md).
