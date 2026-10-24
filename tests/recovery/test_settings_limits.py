"""D096: import time and project size come from Settings and bound new work, never stored projects."""

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from packages.resume_core.background_limits import LIMITS, background_global_bytes, background_project_bytes, import_seconds
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_supervisor import JobControl
from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.project_limits import MIB, USER_LIMITS, apply_preferences, project_file_bytes
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_project_store import RichProjectStore
from packages.resume_core.storage import StorageFailure, atomic_write
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from resume_api.app import create_app
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.test_preferences import MetadataAdapter, ORIGIN, SECRET, client_session
from tests.support.agent import isolated_project
from tests.support.background_publication import PublicationFixture

LEGACY = b'{"schemaVersion":1,"automaticAnalysis":false,"theme":"light","selectedModel":"model-a"}'


def application(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("fixture")
    return create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / "operations", dist=dist,
        connection_adapter=MetadataAdapter(), gui_provider=CreationProvider(), data_root=tmp_path / "store")


def test_older_preferences_read_default_limits_and_saved_limits_keep_other_choices(tmp_path):
    store = PreferencesStore(tmp_path / "store")
    store.load()
    atomic_write(store.path, LEGACY)
    assert (store.load().import_minutes, store.load().project_megabytes) == (60, 64)
    store.save_limits(90, 128)
    saved = PreferencesStore(store.root).load()
    assert (saved.import_minutes, saved.project_megabytes, saved.selected_model, saved.automatic_analysis, saved.theme) == (
        90, 128, "model-a", False, "light")


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"importMinutes": 4, "projectMegabytes": 64}, {"importMinutes": 60, "projectMegabytes": 257},
    {"importMinutes": 12.5, "projectMegabytes": 64}, {"importMinutes": True, "projectMegabytes": 64}, {"importMinutes": 60},
    {"importMinutes": "60", "projectMegabytes": 64}], ids=["below", "above", "fraction", "boolean", "missing", "text"])
async def test_rejected_limits_change_neither_the_file_nor_the_applied_limits(tmp_path, body):
    app = application(tmp_path)
    async with client_session(app) as client:
        assert (await client.put("/v1/settings/limits", json={"importMinutes": 30, "projectMegabytes": 20})).status_code == 200
        path = tmp_path / "store" / "preferences.json"
        before = path.read_bytes()
        refused = await client.put("/v1/settings/limits", json=body)
        assert refused.status_code == 422 and refused.json()["error"]["code"] == "INVALID_REQUEST"
        assert path.read_bytes() == before and (USER_LIMITS.import_minutes, USER_LIMITS.project_megabytes) == (30, 20)


@pytest.mark.asyncio
async def test_saved_limits_apply_now_survive_restart_and_a_failed_write_keeps_them(tmp_path, monkeypatch):
    app = application(tmp_path)
    assert import_seconds() == 3600 and project_file_bytes() == 64 * MIB
    async with client_session(app) as client:
        saved = await client.put("/v1/settings/limits", json={"importMinutes": 90, "projectMegabytes": 128})
        assert saved.status_code == 200 and (saved.json()["importMinutes"], saved.json()["projectMegabytes"]) == (90, 128)
        assert import_seconds() == 90 * 60 and project_file_bytes() == 128 * MIB
        assert background_project_bytes() == 256 * MIB and background_global_bytes() == 2048 * MIB
        def denied(*_args):
            raise StorageFailure("denied")
        with monkeypatch.context() as patch:
            patch.setattr("packages.resume_core.preferences.atomic_write", denied)
            failed = await client.put("/v1/settings/limits", json={"importMinutes": 5, "projectMegabytes": 10})
            assert failed.status_code == 409 and failed.json()["error"]["code"] == "PREFERENCES_SAVE_FAILED"
        assert import_seconds() == 90 * 60
        preferences = (await client.get("/v1/settings/preferences")).json()
        assert (preferences["importMinutes"], preferences["projectMegabytes"]) == (90, 128)
    apply_preferences(None)
    application(tmp_path)
    assert (USER_LIMITS.import_minutes, USER_LIMITS.project_megabytes) == (90, 128)


def test_import_jobs_take_the_settings_time_limit_and_other_jobs_keep_theirs():
    def control(kind, protocol=None, tools=()):
        return JobControl(supervisor=None, job=SimpleNamespace(submission=SimpleNamespace(kind=kind, protocol=protocol, tools=list(tools))))
    USER_LIMITS.import_minutes = 90
    assert control("processing", "template_import_v1").active_seconds == 90 * 60
    assert control("processing", tools=["save_import"]).active_seconds == 90 * 60
    assert control("processing").active_seconds == control("rewrite").active_seconds == LIMITS.active_seconds == 180


def test_project_size_bounds_new_saves_and_a_lowered_limit_keeps_stored_projects_open(tmp_path):
    _agents, store, workspace, _conversation = isolated_project(tmp_path)
    project, checksum = workspace.project_id, store.read_committed(workspace.project_id)[1]
    larger = workspace.model_copy(deep=True)
    larger.title = "x" * MIB
    USER_LIMITS.project_megabytes = 1
    with pytest.raises(ProjectStoreFailure, match="PROJECT_TOO_LARGE"):
        store.save(larger, {}, {})
    assert store.read_committed(project)[1] == checksum
    USER_LIMITS.project_megabytes = 64
    store.save(larger, {}, {})
    USER_LIMITS.project_megabytes = 1
    assert RichProjectStore(tmp_path).read_committed(project)[0].title == larger.title


def test_background_storage_holds_two_project_sizes(tmp_path):
    # A save writes a full copy of the project file there, next to history.
    fixture = PublicationFixture(tmp_path)
    jobs, project = fixture.jobs, fixture.project
    state = jobs.load(project)
    padding = jobs.projects / project / "capacity-padding.bin"
    with padding.open("wb") as stream:
        stream.truncate(2 * MIB)
    padding.chmod(0o600)
    USER_LIMITS.project_megabytes = 1
    with jobs.guard(project), pytest.raises(BackgroundFailure, match="JOB_STORAGE_FULL"):
        jobs._capacity(state, jobs._all())
    USER_LIMITS.project_megabytes = 2
    with jobs.guard(project):
        jobs._capacity(state, jobs._all())


def test_export_saves_get_more_time_with_a_larger_project_size():
    # A save rewrites and re-validates the whole project file; the long CV took 8–10 s per save under load.
    from resume_api.importer.template_checkpoints import TemplateCheckpoints
    publisher = SimpleNamespace(**{name: {} for name in ("template_checkpoint_locks", "template_checkpoint_tasks",
        "template_checkpoint_async_locks", "template_checkpoint_fences", "template_checkpoint_owners")})
    owner = TemplateCheckpoints(publisher, originals={}, wall=lambda: "")
    assert owner.checkpoint_seconds == LIMITS.receipt_seconds + 2 * 64
    USER_LIMITS.project_megabytes = 10
    assert owner.checkpoint_seconds == LIMITS.receipt_seconds + 20
    assert TemplateCheckpoints(publisher, originals={}, wall=lambda: "", checkpoint_seconds=.05).checkpoint_seconds == .05
