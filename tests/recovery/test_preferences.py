"""Private nonsecret preferences and zero-probe connection reads."""

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import stat
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'services/api/src'))

from packages.resume_core.preferences import PreferencesStore, PreferencesFailure
from packages.resume_core.rules import RulesStore
from packages.resume_core.storage import atomic_write
from resume_api.app import create_app
from resume_api.connection import Metadata, Quota
from tests.recovery.generation_fixtures import CreationProvider, frozen_now
from tests.recovery.candidate_fixtures import ROOT

ORIGIN='http://127.0.0.1:39272';SECRET='synthetic-preferences-secret-0123456789'


def test_private_preferences_keep_defaults_model_and_unrelated_fields_on_restart(tmp_path):
    root=tmp_path/'FoldCV';RulesStore(root).load();store=PreferencesStore(root)
    initial=store.load();assert initial.automatic_analysis and initial.theme=='system' and initial.selected_model is None
    selected=store.select_model('reported-model-a');assert selected.selected_model=='reported-model-a'
    assert PreferencesStore(root).load()==selected and selected.automatic_analysis==initial.automatic_analysis
    assert stat.S_IMODE(root.stat().st_mode)==0o700 and stat.S_IMODE(store.path.stat().st_mode)==0o600
    assert set(json.loads(store.path.read_text()))=={'schemaVersion','automaticAnalysis','theme','selectedModel','selectedImportModel','rewriteReasoningEffort'}


def test_preferences_invalid_model_corrupt_json_and_symlink_fail_without_reset_or_leak(tmp_path,capsys):
    root=tmp_path/'FoldCV';RulesStore(root).load();store=PreferencesStore(root);store.select_model('model-a');before=store.path.read_bytes()
    with pytest.raises(PreferencesFailure,match='MODEL_DENIED'):store.select_model('email@example.invalid')
    assert store.path.read_bytes()==before
    atomic_write(store.path,b'{"schemaVersion":1,"schemaVersion":1}')
    with pytest.raises(PreferencesFailure,match='PREFERENCES_CORRUPT'):store.load()
    assert store.path.read_bytes()==b'{"schemaVersion":1,"schemaVersion":1}'
    store.path.unlink();outside=tmp_path/'outside';outside.write_text('private-value');store.path.symlink_to(outside)
    with pytest.raises(PreferencesFailure,match='PREFERENCES_UNAVAILABLE'):store.load()
    assert outside.read_text()=='private-value' and capsys.readouterr()==('','')


def test_failed_preference_write_preserves_acknowledged_model(tmp_path,monkeypatch):
    root=tmp_path/'FoldCV';RulesStore(root).load();store=PreferencesStore(root);store.select_model('model-a');before=store.path.read_bytes()
    from packages.resume_core.storage import StorageFailure
    def denied(*_args):raise StorageFailure('denied')
    monkeypatch.setattr('packages.resume_core.preferences.atomic_write',denied)
    with pytest.raises(PreferencesFailure,match='PREFERENCES_SAVE_FAILED'):store.select_model('model-b')
    assert store.path.read_bytes()==before


class MetadataAdapter:
    def __init__(self):self.inspections=0;self.logins=0
    def inspect(self,_files,_cancel,*,full=True):
        self.inspections+=1;return Metadata('fixture-cli',('model-a','model-b'),'plus',Quota('available',25))
    def login(self,_files,_cancel):self.logins+=1;raise AssertionError('native login')


def application(tmp_path, adapter, provider):
    dist=tmp_path/'dist';dist.mkdir(exist_ok=True);(dist/'index.html').write_text('fixture')
    return create_app(origin=ORIGIN,secret=SECRET,temp_root=tmp_path/'operations',dist=dist,
        connection_adapter=adapter,gui_provider=provider,gui_clock=frozen_now,data_root=tmp_path/'FoldCV')


@asynccontextmanager
async def client_session(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=ORIGIN,headers={'Origin':ORIGIN}) as client:
        assert (await client.post('/v1/session/exchange',json={'secret':SECRET})).status_code==200
        yield client


@pytest.mark.asyncio
async def test_settings_open_reads_connection_and_preferences_without_probe_login_or_content(tmp_path):
    adapter=MetadataAdapter();provider=CreationProvider();app=application(tmp_path,adapter,provider)
    async with client_session(app) as client:
        connection=await client.get('/v1/settings/connection');preferences=await client.get('/v1/settings/preferences')
        assert connection.status_code==preferences.status_code==200 and connection.json()['state']=='unchecked'
        assert preferences.json()['automaticAnalysis'] is True
    assert adapter.inspections==adapter.logins==0 and provider.calls==[]


@pytest.mark.asyncio
async def test_reported_model_selection_persists_and_reaches_both_creation_requests(tmp_path):
    adapter=MetadataAdapter();provider=CreationProvider();app=application(tmp_path,adapter,provider)
    async with client_session(app) as client:
        assert (await client.post('/v1/host/status',json={})).json()['metadataReady']
        assert (await client.post('/v1/host/select',json={'model':'model-b'})).json()['selectedModel']=='model-b'
        selected=[]
        generate=provider.generate
        def capture(request,*args):selected.append(request.policy.model);return generate(request,*args)
        provider.generate=capture
        response=await client.post('/v1/projects',json={'text':(ROOT/'E1.txt').read_text()});assert response.status_code==202
        id=response.json()['workspace']['projectId'];gid=response.json()['generationId']
        await asyncio.wait_for(app.app.state.gui_projects.tasks[(id,gid)],40)
        assert selected==['model-b','model-b'] and adapter.logins==0
        assert (await client.get('/v1/settings/preferences')).json()['selectedModel']=='model-b'
    restarted=application(tmp_path,MetadataAdapter(),CreationProvider())
    async with client_session(restarted) as client:
        assert (await client.get('/v1/settings/connection')).json()['state']=='unchecked'
        assert (await client.post('/v1/host/status',json={})).json()['selectedModel']=='model-b'


@pytest.mark.asyncio
async def test_denied_model_and_failed_save_keep_runtime_choice_and_project_unchanged(tmp_path,monkeypatch):
    adapter=MetadataAdapter();app=application(tmp_path,adapter,CreationProvider())
    async with client_session(app) as client:
        await client.post('/v1/host/status',json={});await client.post('/v1/host/select',json={'model':'model-a'})
        assert (await client.post('/v1/host/select',json={'model':'unreported'})).status_code==409
        from packages.resume_core.storage import StorageFailure
        def denied(*_args):raise StorageFailure('denied')
        monkeypatch.setattr('packages.resume_core.preferences.atomic_write',denied)
        assert (await client.post('/v1/host/select',json={'model':'model-b'})).status_code==409
        assert (await client.get('/v1/settings/connection')).json()['selectedModel']=='model-a'


@pytest.mark.asyncio
async def test_injected_connection_without_data_override_never_opens_default_user_store(tmp_path,monkeypatch):
    dist=tmp_path/'dist';dist.mkdir();(dist/'index.html').write_text('fixture')
    app=create_app(origin=ORIGIN,secret=SECRET,temp_root=tmp_path/'operations',dist=dist,connection_adapter=MetadataAdapter())
    async with client_session(app) as client:
        await client.post('/v1/host/status',json={});await client.post('/v1/host/select',json={'model':'model-a'})
    assert (tmp_path/'FoldCV/preferences.json').is_file() and (tmp_path/'FoldCV/rules.md').is_file()
