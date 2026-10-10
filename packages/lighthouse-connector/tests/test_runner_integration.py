"""aria-runner execute → Lighthouse connector, with Meltano replaced by a recorder."""

from __future__ import annotations

from pathlib import Path

import pytest
from aria_runner import service
from aria_runner.connectors import ConnectorManifest
from aria_runner.db import Database, RunStatus
from aria_runner.execute import execute_run
from aria_runner.launcher import LaunchResult
from aria_runner.sessions import FileSessionStore
from aria_runner.settings import Settings
from test_connector import ROOT, SLUG, FakeRunner

from lighthouse_connector import runtime
from lighthouse_connector.local import connections_payload
from lighthouse_connector.manifest import manifest

SESSION = b'{"cookies": [{"name": "sid", "value": "v"}], "origins": []}'


class NoopLauncher:
    def launch(self, run_id: str, _manifest: ConnectorManifest) -> LaunchResult:
        return LaunchResult(execution_name=f"test-{run_id[:8]}")


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    from aria_runner.migrate import upgrade

    settings = Settings(
        org_id="1782243883257222643",
        database_url=f"sqlite:///{tmp_path / 'r.db'}",
        session_store_uri=f"file://{tmp_path / 'sessions'}",
        launcher="local",
        tmp_root=str(tmp_path),
    )
    upgrade(settings.database_url)
    db = Database(settings.database_url)
    store = FileSessionStore(settings.session_store_uri)
    service.put_connector(db, ConnectorManifest.model_validate(manifest()))
    [row] = connections_payload(ROOT)
    service.put_connection(
        db, settings, row["id"], connector_key="lighthouse", name=row["name"], config=row["config"]
    )
    uri = store.uri_for(settings.org_id, SLUG)
    store.write(uri, SESSION)
    service.mark_session_saved(db, SLUG, uri)
    monkeypatch.setenv("MELTANO_PROJECT_ROOT", str(ROOT))
    return settings, db, store


def test_two_runs_carry_bookmarks_through_postgres(env, monkeypatch) -> None:  # noqa: ANN001
    settings, db, store = env
    runners: list[FakeRunner] = []

    def make_runner(_ctx):  # noqa: ANN001, ANN202
        runner = FakeRunner(state_out=f'{{"singer_state": {{"n": {len(runners) + 1}}}}}')
        runners.append(runner)
        return runner

    monkeypatch.setattr(runtime, "ContextRunner", make_runner)
    connector = runtime.LighthouseConnector()
    monkeypatch.setattr(connector, "probe", lambda ctx: None)

    for _ in range(2):
        run = service.enqueue_run(db, settings, NoopLauncher(), SLUG, {"environment": "development"})
        assert execute_run(
            run.id, db=db, settings=settings, store=store, connector_loader=lambda _k: connector
        ) == 0
        done = service.get_run(db, settings, run.id)
        assert done.status == RunStatus.succeeded, done.error

    first, second = runners
    assert not any("state set" in " ".join(argv) for argv, _ in first.calls)
    seeded = [argv for argv, _ in second.calls if "set" in argv]
    assert seeded and seeded[0][-1] == '{"singer_state": {"n": 1}}'
    assert service.get_state(db, settings, SLUG).state == {"development": {"singer_state": {"n": 2}}}
