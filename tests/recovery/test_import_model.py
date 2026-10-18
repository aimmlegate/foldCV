"""Import model choice persists independently and is captured before execution."""

import asyncio
from pathlib import Path
import sys

import pytest

from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.preferences import PreferencesFailure, PreferencesStore
from packages.resume_core.storage import StorageFailure, atomic_write
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from resume_api.agent.runtime import RuntimeResult
from resume_api.app import create_app
from resume_api.gui_projects import ProjectFailure
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.test_background_fixed_jobs import fixed_request, settled
from tests.recovery.test_preferences import MetadataAdapter, ORIGIN, SECRET, client_session
from tests.support.importing import complete, importer


def application(tmp_path, runtime, queued=False):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("fixture")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
        connection_adapter=MetadataAdapter(), gui_provider=CreationProvider(), agent_runtime=runtime,
        background_enabled=queued, data_root=tmp_path / "store")


def test_legacy_preferences_import_override_and_other_choices_survive_restart(tmp_path):
    store = PreferencesStore(tmp_path / "store")
    store.load()
    atomic_write(store.path, b'{"schemaVersion":1,"automaticAnalysis":false,"theme":"light","selectedModel":"model-a"}')
    assert store.load().selected_import_model is None
    store.select_import_model("model-b")
    store.select_model("model-c")
    store.save_analysis(True)
    saved = PreferencesStore(store.root).load()
    assert (saved.selected_model, saved.selected_import_model, saved.automatic_analysis, saved.theme) == (
        "model-c", "model-b", True, "light")
    store.select_import_model(None)
    assert PreferencesStore(store.root).load().selected_import_model is None
    before = store.path.read_bytes()
    with pytest.raises(PreferencesFailure, match="MODEL_DENIED"):
        store.select_import_model("invalid/model")
    assert store.path.read_bytes() == before
    atomic_write(store.path, before.replace(b'"selectedImportModel": null', b'"selectedImportModel": "invalid/model"'))
    with pytest.raises(PreferencesFailure, match="PREFERENCES_CORRUPT"):
        store.load()


@pytest.mark.asyncio
async def test_import_setting_validates_catalog_and_failed_writes_without_changing_other_models(tmp_path, monkeypatch):
    runtime, _ = importer(monkeypatch)
    app = application(tmp_path, runtime)
    async with app.app.router.lifespan_context(app.app), client_session(app) as client:
        path = "/v1/settings/import-model"
        assert (await client.put(path, json={"model": "model-b"})).status_code == 409
        await client.post("/v1/host/status", json={})
        await client.post("/v1/host/select", json={"model": "model-a"})
        assistant = AgentSettingsStore(tmp_path / "store").load()
        saved = await client.put(path, json={"model": "model-b"})
        assert saved.status_code == 200 and saved.json()["selectedImportModel"] == "model-b"
        assert (await client.put(path, json={"model": "unlisted"})).status_code == 409
        assert (await client.put(path, json={"model": "invalid/model"})).status_code == 422
        assert (await client.put(path, json={})).status_code == 422
        def denied(*_args):
            raise StorageFailure("denied")
        with monkeypatch.context() as patch:
            patch.setattr("packages.resume_core.preferences.atomic_write", denied)
            failed = await client.put(path, json={"model": "model-a"})
            assert failed.status_code == 409
        preferences = (await client.get("/v1/settings/preferences")).json()
        assert preferences["selectedImportModel"] == "model-b" and preferences["selectedModel"] == "model-a"
        assert (await client.get("/v1/settings/connection")).json()["selectedModel"] == "model-a"
        assert AgentSettingsStore(tmp_path / "store").load() == assistant
        assert app.app.state.rich_projects.provider_factory()[1] == "model-a"
    restarted = application(tmp_path, runtime)
    async with restarted.app.router.lifespan_context(restarted.app), client_session(restarted) as client:
        assert (await client.get("/v1/settings/preferences")).json()["selectedImportModel"] == "model-b"
        assert (await client.put("/v1/settings/import-model", json={"model": None})).status_code == 200
    assert runtime.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("queued", [False, True])
@pytest.mark.parametrize("override", [None, "model-b"])
async def test_import_captures_override_or_default_before_later_settings_changes(tmp_path, monkeypatch, queued, override):
    entered, release = asyncio.Event(), asyncio.Event()
    async def turn(session, value, cancel):
        entered.set()
        await release.wait()
        await complete(session)
        return RuntimeResult(state="completed")
    runtime, _ = importer(monkeypatch, turn)
    app = application(tmp_path, runtime, queued)
    async with app.app.router.lifespan_context(app.app), client_session(app) as client:
        await client.post("/v1/host/status", json={})
        await client.post("/v1/host/select", json={"model": "model-a"})
        assert (await client.put("/v1/settings/import-model", json={"model": override})).status_code == 200
        projects, jobs = app.app.state.rich_projects, app.app.state.jobs
        source = await projects.select(Path("tests/fixtures/recovery/E1.txt").read_bytes(), "pasted.txt", True)
        identifier = source.project_id
        expected = override or "model-a"
        try:
            if queued:
                jobs.supervisor.dispatch_enabled = False
                reply, _ = await jobs.fixed.submit(identifier, fixed_request(jobs, identifier, "import", {"kind": "processing"}))
                assert reply.job.submission.models[0].model == expected
            else:
                generation = projects.start(identifier)
            started = projects.response(identifier).generation.started_at
            assert started and (not queued or started == reply.job.created_at)
            changed = "model-a" if override else "model-b"
            await client.put("/v1/settings/import-model", json={"model": changed})
            if queued:
                jobs.supervisor.dispatch_enabled = True
                jobs.supervisor.changed.set()
            await asyncio.wait_for(entered.wait(), 10)
            assert projects.response(identifier).generation.started_at == started
            release.set()
            if queued:
                done = await settled(jobs, identifier, reply.job.id, publication="saved")
                assert done.receipt is not None
            else:
                await asyncio.wait_for(projects.tasks[(identifier, generation)], 10)
                assert projects.generations[identifier].status == "completed"
            assert runtime.calls == [expected]
            assert projects.import_provider_factory()[1] == changed
            assert projects.provider_factory()[1] == "model-a"
        finally:
            release.set()


@pytest.mark.asyncio
async def test_unavailable_import_choice_has_no_fallback_and_needs_no_editing_model(tmp_path, monkeypatch):
    runtime, _ = importer(monkeypatch)
    app = application(tmp_path, runtime)
    async with app.app.router.lifespan_context(app.app), client_session(app) as client:
        await client.post("/v1/host/status", json={})
        assert (await client.put("/v1/settings/import-model", json={"model": "model-b"})).status_code == 200
        projects = app.app.state.rich_projects
        assert (await client.get("/v1/settings/connection")).json()["selectedModel"] is None
        assert projects.import_provider_factory()[1] == "model-b"
        source = await projects.select(Path("tests/fixtures/recovery/E1.txt").read_bytes(), "pasted.txt", True)
        PreferencesStore(tmp_path / "store").select_import_model("removed-model")
        with pytest.raises(ProjectFailure, match="MODEL_DENIED"):
            projects.start(source.project_id)
        assert runtime.calls == [] and projects.read(source.project_id).project is None
