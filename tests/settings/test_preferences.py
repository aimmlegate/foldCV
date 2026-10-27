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
    assert initial.automatic_analysis and initial.theme == 'system' and initial.selected_model is None
    selected = store.select_model('reported-model-a')
    assert selected.selected_model == 'reported-model-a'
    assert PreferencesStore(root).load() == selected and selected.automatic_analysis == initial.automatic_analysis
    assert stat.S_IMODE(root.stat().st_mode) == 0o700 and stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert set(json.loads(store.path.read_text())) == {'schemaVersion', 'automaticAnalysis', 'theme', 'selectedModel',
        'selectedImportModel', 'selectedFallbackModel', 'rewriteReasoningEffort', 'importMinutes', 'projectMegabytes',
        'selectedProvider', 'providerSelections'}


def test_preferences_from_before_providers_load_as_codex(tmp_path):
    root = tmp_path / 'FoldCV'
    RulesStore(root).load()
    store = PreferencesStore(root)
    atomic_write(store.path, json.dumps({'schemaVersion': 1, 'automaticAnalysis': False, 'theme': 'dark',
        'selectedModel': 'model-a', 'selectedImportModel': 'model-b', 'rewriteReasoningEffort': 'high'}).encode())
    value = store.load()
    assert value.selected_provider == 'codex_cli' and value.provider_selections == {}
    assert (value.selected_model, value.selected_import_model, value.rewrite_reasoning_effort) == ('model-a', 'model-b', 'high')
    assert not value.automatic_analysis and value.theme == 'dark'


def test_provider_switch_keeps_and_restores_each_providers_choices(tmp_path):
    root = tmp_path / 'FoldCV'
    RulesStore(root).load()
    store = PreferencesStore(root)
    store.select_model('model-a')
    store.select_import_model('model-b')
    store.select_fallback_model('model-c')
    store.select_rewrite_reasoning('model-a', 'high')
    value, agent = store.select_provider('claude_cli', 'agent-a', 'low')
    assert value.selected_provider == 'claude_cli' and agent == (None, None)
    assert (value.selected_model, value.selected_import_model, value.selected_fallback_model,
            value.rewrite_reasoning_effort) == (None, None, None, None)
    store.select_model('claude-model')
    value, agent = store.select_provider('codex_cli', 'agent-b', 'max')
    assert agent == ('agent-a', 'low') and value.selected_provider == 'codex_cli'
    assert (value.selected_model, value.selected_import_model, value.selected_fallback_model,
            value.rewrite_reasoning_effort) == ('model-a', 'model-b', 'model-c', 'high')
    assert set(value.provider_selections) == {'claude_cli'}
    value, agent = store.select_provider('claude_cli', 'agent-a', 'low')
    assert value.selected_model == 'claude-model' and agent == ('agent-b', 'max')
    assert store.select_provider('claude_cli', 'agent-x', None) == (store.load(), ('agent-x', None))


@pytest.mark.parametrize('change', [
    {'selectedProvider': 'grok_cli'},
    {'providerSelections': {'codex_cli': {'selectedModel': 'model-a'}}},
    {'selectedProvider': 'claude_cli', 'providerSelections': {'claude_cli': {}}},
    {'providerSelections': {'claude_cli': {'selectedAgentModel': 'email@example.invalid'}}},
])
def test_invalid_provider_preferences_are_corrupt_without_reset(tmp_path, change):
    root = tmp_path / 'FoldCV'
    RulesStore(root).load()
    store = PreferencesStore(root)
    raw = json.dumps({'schemaVersion': 1, 'automaticAnalysis': True, 'theme': 'system', 'selectedModel': None,
                      **change}).encode()
    atomic_write(store.path, raw)
    with pytest.raises(PreferencesFailure, match='PREFERENCES_CORRUPT'):
        store.load()
    assert store.path.read_bytes() == raw


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
        assert preferences.json()['automaticAnalysis'] is True
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
