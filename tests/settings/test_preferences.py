"""Private nonsecret preferences, the editing model choice and zero-probe settings reads."""

import json
import stat

import pytest

from packages.resume_core.preferences import PreferencesFailure, PreferencesStore
from packages.resume_core.rules import RulesStore
from packages.resume_core.storage import StorageFailure, atomic_write
from resume_api.app import create_app
from tests.settings.support import ORIGIN, SECRET, MetadataAdapter, application, client_session
from tests.support.generation import CreationProvider


def test_private_preferences_keep_defaults_model_and_unrelated_fields_on_restart(tmp_path):
    root = tmp_path / 'FoldCV'
    RulesStore(root).load()
    store = PreferencesStore(root)
    initial = store.load()
    assert not initial.automatic_analysis and initial.theme == 'system' and initial.selected_model is None
    selected = store.select_model('reported-model-a')
    assert selected.selected_model == 'reported-model-a'
    assert PreferencesStore(root).load() == selected and selected.automatic_analysis == initial.automatic_analysis
    assert stat.S_IMODE(root.stat().st_mode) == 0o700 and stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert set(json.loads(store.path.read_text())) == {'schemaVersion', 'automaticAnalysis', 'theme', 'selectedModel',
        'selectedImportModel', 'selectedFallbackModel', 'rewriteReasoningEffort', 'importMinutes', 'projectMegabytes'}


def test_an_older_stored_automatic_check_choice_stays_readable_and_unchanged(tmp_path):
    root = tmp_path / 'FoldCV'
    RulesStore(root).load()
    store = PreferencesStore(root)
    older = b'{"schemaVersion":1,"automaticAnalysis":true,"theme":"light","selectedModel":"model-a"}'
    atomic_write(store.path, older)
    assert store.load().automatic_analysis is True and store.path.read_bytes() == older
    assert store.select_model('model-b').automatic_analysis is True


def test_preferences_invalid_model_corrupt_json_and_symlink_fail_without_reset_or_leak(tmp_path, capsys):
    root = tmp_path / 'FoldCV'
    RulesStore(root).load()
    store = PreferencesStore(root)
    store.select_model('model-a')
    before = store.path.read_bytes()
    with pytest.raises(PreferencesFailure, match='MODEL_DENIED'):
        store.select_model('email@example.invalid')
    assert store.path.read_bytes() == before
    atomic_write(store.path, b'{"schemaVersion":1,"schemaVersion":1}')
    with pytest.raises(PreferencesFailure, match='PREFERENCES_CORRUPT'):
        store.load()
    assert store.path.read_bytes() == b'{"schemaVersion":1,"schemaVersion":1}'
    store.path.unlink()
    outside = tmp_path / 'outside'
    outside.write_text('private-value')
    store.path.symlink_to(outside)
    with pytest.raises(PreferencesFailure, match='PREFERENCES_UNAVAILABLE'):
        store.load()
    assert outside.read_text() == 'private-value' and capsys.readouterr() == ('', '')


def test_failed_preference_write_preserves_acknowledged_model(tmp_path, monkeypatch):
    root = tmp_path / 'FoldCV'
    RulesStore(root).load()
    store = PreferencesStore(root)
    store.select_model('model-a')
    before = store.path.read_bytes()

    def denied(*_args):
        raise StorageFailure('denied')
    monkeypatch.setattr('packages.resume_core.preferences.atomic_write', denied)
    with pytest.raises(PreferencesFailure, match='PREFERENCES_SAVE_FAILED'):
        store.select_model('model-b')
    assert store.path.read_bytes() == before


@pytest.mark.asyncio
async def test_settings_open_reads_connection_and_preferences_without_probe_login_or_content(tmp_path):
    adapter, provider = MetadataAdapter(), CreationProvider()
    app = application(tmp_path, adapter, provider)
    async with client_session(app) as client:
        connection = await client.get('/v1/settings/connection')
        preferences = await client.get('/v1/settings/preferences')
        assert connection.status_code == preferences.status_code == 200 and connection.json()['state'] == 'unchecked'
        assert preferences.json()['automaticAnalysis'] is False
    assert adapter.inspections == adapter.logins == 0 and provider.calls == []


@pytest.mark.asyncio
async def test_a_reported_model_selection_survives_restart_without_a_probe_or_login(tmp_path):
    adapter = MetadataAdapter()
    async with client_session(application(tmp_path, adapter)) as client:
        assert (await client.post('/v1/host/status', json={})).json()['metadataReady']
        assert (await client.post('/v1/host/select', json={'model': 'model-b'})).json()['selectedModel'] == 'model-b'
        assert (await client.get('/v1/settings/preferences')).json()['selectedModel'] == 'model-b'
    assert adapter.logins == 0
    restarted = MetadataAdapter()
    async with client_session(application(tmp_path, restarted)) as client:
        assert (await client.get('/v1/settings/connection')).json()['state'] == 'unchecked'
        assert restarted.inspections == 0
        assert (await client.post('/v1/host/status', json={})).json()['selectedModel'] == 'model-b'


@pytest.mark.asyncio
async def test_denied_model_and_failed_save_keep_runtime_choice(tmp_path, monkeypatch):
    async with client_session(application(tmp_path)) as client:
        await client.post('/v1/host/status', json={})
        await client.post('/v1/host/select', json={'model': 'model-a'})
        assert (await client.post('/v1/host/select', json={'model': 'unreported'})).status_code == 409

        def denied(*_args):
            raise StorageFailure('denied')
        monkeypatch.setattr('packages.resume_core.preferences.atomic_write', denied)
        assert (await client.post('/v1/host/select', json={'model': 'model-b'})).status_code == 409
        assert (await client.get('/v1/settings/connection')).json()['selectedModel'] == 'model-a'


@pytest.mark.asyncio
async def test_injected_connection_without_data_override_never_opens_default_user_store(tmp_path, monkeypatch):
    # If the injected-connection fallback regressed to the default store, HOME keeps that write inside tmp_path.
    monkeypatch.setenv('HOME', str(tmp_path))
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('fixture')
    app = create_app(origin=ORIGIN, secret=SECRET, temp_root=tmp_path / 'operations', dist=dist,
        connection_adapter=MetadataAdapter())
    async with client_session(app) as client:
        await client.post('/v1/host/status', json={})
        await client.post('/v1/host/select', json={'model': 'model-a'})
    assert (tmp_path / 'FoldCV/preferences.json').is_file() and (tmp_path / 'FoldCV/rules.md').is_file()
    assert not (tmp_path / 'Library').exists()
