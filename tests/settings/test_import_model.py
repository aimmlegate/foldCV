"""PUT /v1/settings/import-model: the import model persists apart from the editing model and is captured at import start."""

import pytest

from packages.resume_core.agent_settings import AgentSettingsStore
from packages.resume_core.preferences import PreferencesFailure, PreferencesStore
from packages.resume_core.storage import StorageFailure, atomic_write
from resume_api.projects.errors import ProjectFailure
from tests.settings.support import application, client_session


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
    app = application(tmp_path, template_import_call_cap=4)
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
        assert app.app.state.intake.model().model == "model-b"
    restarted = application(tmp_path, template_import_call_cap=4)
    async with restarted.app.router.lifespan_context(restarted.app), client_session(restarted) as client:
        assert (await client.get("/v1/settings/preferences")).json()["selectedImportModel"] == "model-b"
        assert (await client.put("/v1/settings/import-model", json={"model": None})).status_code == 200


@pytest.mark.asyncio
async def test_an_unavailable_import_choice_has_no_fallback_and_needs_no_editing_model(tmp_path):
    app = application(tmp_path, template_import_call_cap=4)
    async with app.app.router.lifespan_context(app.app), client_session(app) as client:
        await client.post("/v1/host/status", json={})
        assert (await client.put("/v1/settings/import-model", json={"model": "model-b"})).status_code == 200
        assert (await client.get("/v1/settings/connection")).json()["selectedModel"] is None
        intake = app.app.state.intake
        assert intake.model().model == "model-b"
        PreferencesStore(tmp_path / "store").select_import_model("removed-model")
        with pytest.raises(ProjectFailure, match="MODEL_DENIED"):
            intake.model()
