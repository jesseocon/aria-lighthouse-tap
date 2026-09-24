# cookiecutter-tap-browser

Scaffold a new Playwright-backed Singer tap in `packages/tap-<site>/`.

```bash
cd /path/to/aria-lighthouse
cookiecutter cookiecutter-tap-browser -o packages
```

Then add the generated extractor block from `meltano.plugin.yml.snippet` to root `meltano.yml`.
