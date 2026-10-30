"""PUT /v1/settings/limits (D096): import time and project size come from Settings and apply at once."""

import pytest

from packages.resume_core.preferences import PreferencesStore
from packages.resume_core.project_limits import MIB, USER_LIMITS, apply_preferences, import_seconds, project_file_bytes
from packages.resume_core.storage import StorageFailure, atomic_write
from tests.settings.support import application, client_session

LEGACY = b'{"schemaVersion":1,"automaticAnalysis":false,"theme":"light","selectedModel":"model-a"}'


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


@pytest.mark.asyncio
async def test_a_full_disk_during_a_limits_save_gives_the_preferences_code(tmp_path, monkeypatch):
    app = application(tmp_path)
    async with client_session(app) as client:
        assert (await client.put("/v1/settings/limits", json={"importMinutes": 90, "projectMegabytes": 128})).status_code == 200

        def full(*_args):
            raise OSError(28, "No space left on device")
        monkeypatch.setattr("packages.resume_core.preferences.atomic_write", full)
        failed = await client.put("/v1/settings/limits", json={"importMinutes": 5, "projectMegabytes": 10})
        assert failed.status_code == 409 and failed.json()["error"]["code"] == "PREFERENCES_SAVE_FAILED"
    assert import_seconds() == 90 * 60 and project_file_bytes() == 128 * MIB


def test_a_broken_preferences_lock_at_startup_falls_back_to_default_limits(tmp_path):
    application(tmp_path)
    store = PreferencesStore(tmp_path / "store")
    store.save_limits(90, 128)
    (tmp_path / "store" / ".preferences.lock").unlink()
    (tmp_path / "store" / ".preferences.lock").mkdir()
    application(tmp_path)
    assert (USER_LIMITS.import_minutes, USER_LIMITS.project_megabytes) == (60, 64)


def test_limits_belong_to_the_process_so_a_second_app_replaces_the_first_apps_limits(tmp_path):
    # The rule is one app per process: production has one, and the autouse fixture resets the limits between tests.
    first = tmp_path / "first"
    first.mkdir()
    application(first)
    PreferencesStore(first / "store").save_limits(90, 12)
    application(first)
    assert project_file_bytes() == 12 * MIB
    second = tmp_path / "second"
    second.mkdir()
    application(second)
    assert project_file_bytes() == 64 * MIB
