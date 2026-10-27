"""aria-runner entry point for Lighthouse."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aria_runner.sdk import LoginHandoff, ReauthRequired, RunContext, RunResult

from lighthouse_connector.manifest import KEY, manifest
from lighthouse_connector.plan import build_plan
from lighthouse_connector.sync import MeltanoSync


def project_root() -> Path:
    configured = os.environ.get("MELTANO_PROJECT_ROOT")
    if configured:
        return Path(configured)
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "meltano.yml").is_file():
            return candidate
    raise FileNotFoundError("meltano.yml not found; set MELTANO_PROJECT_ROOT")


class ContextRunner:
    """Meltano subprocesses through the run context: logged, cancellable."""

    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        cwd: Path,
        on_line: Callable[[str], None] | None = None,
        step: str | None = None,
    ) -> None:
        self.ctx.run_command(argv, env=env, cwd=cwd, on_line=on_line, step=step)

    def output(self, argv: Sequence[str], *, env: Mapping[str, str], cwd: Path) -> str:
        return self.ctx.capture_output(argv, env=env, cwd=cwd)


class LighthouseConnector:
    key = KEY

    def manifest(self) -> dict[str, Any]:
        return manifest()

    def probe(self, ctx: RunContext) -> None:
        return None

    def release_login(self, handoff: LoginHandoff, logger: logging.Logger) -> str:
        """End of a login chain: log out of Lighthouse with the handed-over session, headed."""
        from playwright.sync_api import sync_playwright
        from tap_lighthouse import signout

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            try:
                context = browser.new_context(storage_state=str(handoff.path), viewport={"width": 1600, "height": 1000})
                page = context.new_page()
                page.goto(signout.APP_HOME, wait_until="load", timeout=60_000)
                how = signout.sign_out(page)
            finally:
                browser.close()
        logger.info("Signed out of Lighthouse at the end of the login chain (%s)", how)
        return f"Signed out of Lighthouse at the end of the login chain ({how})"

    def run(self, ctx: RunContext) -> RunResult:
        if not ctx.params.get("transform_only"):
            if not ctx.secret_env.get("TAP_LIGHTHOUSE_USERNAME") or not ctx.secret_env.get(
                "TAP_LIGHTHOUSE_PASSWORD"
            ):
                raise ReauthRequired(
                    "Lighthouse username and password are not saved on this connection"
                )
        plan = build_plan(
            ctx.config,
            ctx.params,
            slug=ctx.connection_id,
            secret_env=ctx.secret_env,
            handoff_path=ctx.login_handoff.path if ctx.login_handoff is not None else None,
        )
        ctx.logger.info(
            "lighthouse %s: scrape=%s targets=%s state_id=%s",
            plan.slug,
            plan.scrape_env if plan.scrape else "skip",
            ",".join(plan.target_envs),
            plan.state_id,
        )
        sync = MeltanoSync(
            project_root(),
            ContextRunner(ctx),
            system_db_uri=f"sqlite:///{ctx.work_dir / 'meltano.db'}",
        )
        prior = (ctx.state or {}).get(plan.scrape_env)
        singer_state, metrics = sync.execute(plan, prior_state=prior, manage_state=True)
        if plan.scrape is None or singer_state is None:
            return RunResult(state=None, metrics=metrics)
        return RunResult(state={**(ctx.state or {}), plan.scrape_env: singer_state}, metrics=metrics)
