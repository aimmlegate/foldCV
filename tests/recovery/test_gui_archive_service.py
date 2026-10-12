"""Separate durable import identities and protected portable transfer APIs."""

import asyncio
from pathlib import Path
import sys
import pytest
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'services/api/src'))
from packages.resume_core.gui_archive_zip import read_zip,parse_json
from packages.resume_core.gui_projects import GuiArchiveRequest
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.preferences import PreferencesStore
from resume_api.app import create_app
from resume_api.gui_projects import ProjectFailure
from tests.recovery.test_project_store import created,service,edit_request
from tests.recovery.test_gui_mutations import mutation
from tests.recovery.test_gui_exports import exported,CountingRenderer
from tests.recovery.test_gui_rewriting import request as rewrite_request
from tests.recovery.test_gui_migrations import legacy_v3,v2
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.candidate_fixtures import ROOT
from packages.resume_core.gui_archive_zip import write_zip


def request(workspace):return GuiArchiveRequest(projectRevision=workspace.project_revision,documentRevision=workspace.document_revision)


@pytest.mark.asyncio
async def test_portable_save_packages_only_current_docx_sources_and_workspace_then_import_regenerates_cache(tmp_path):
    store,id=await created(tmp_path);before=store.read(id);store.provider_factory=lambda:pytest.fail('portable transfer inferred')
    data=await store.portable_archive(id,request(before));files=read_zip(data);manifest=parse_json(files['manifest.json'])
    assert {entry['role'] for entry in manifest['entries']}=={'workspace','source_original','render'} and len([entry for entry in manifest['entries'] if entry['role']=='render'])==1
    assert not any(path.startswith('template/') for path in files)
    imported=await store.import_archive(data);after=store.read(imported)
    assert imported!=id and after.project.document==before.project.document and after.project.renders[0].model_dump(exclude={'artifact_available'})==before.project.renders[0].model_dump(exclude={'artifact_available'})
    assert all(not render.artifact_available for render in after.project.renders) and not any(key[0]==imported for key in store.artifacts)
    renderer=CountingRenderer();store.renderer=renderer
    result,operation=await exported(store,imported);assert operation.status=='completed' and renderer.calls==1 and store.export_artifact(imported,operation.id)
    assert store.read(id).model_dump()==before.model_dump()


@pytest.mark.asyncio
async def test_round_trip_new_identity_clears_replay_preserves_open_session_sources_globals_and_stored_date(tmp_path):
    store,id=await created(tmp_path);store.preferences=PreferencesStore(store.rules.root);store.preferences.save_analysis(False)
    first=edit_request(store.read(id),'Saved prior',completion='slot',id='same-mutation');store.mutate(id,first);store.mutate(id,edit_request(store.read(id),'Open current',session='open',completion='none'))
    rules=store.rules.root/'rules.md';preferences=store.rules.root/'preferences.json';globals=(rules.read_bytes(),preferences.read_bytes());before=store.read(id)
    data=await store.portable_archive(id,request(before));store.provider_factory=lambda:pytest.fail('transfer inferred')
    imported=await store.import_archive(data);after=store.read(imported)
    assert after.undo_slots==before.undo_slots and after.edit_sessions==before.edit_sessions and after.mutation_replay==[] and after.formatting_as_of==before.formatting_as_of
    assert (rules.read_bytes(),preferences.read_bytes())==globals
    assert {sid:value for (pid,sid),value in store.originals.items() if pid==imported}=={sid:value for (pid,sid),value in store.originals.items() if pid==id}
    assert store.mutate(imported,edit_request(after,'New import edit',session='open',id='same-mutation')).status=='applied'
    reopened=service(tmp_path,CreationProvider());assert reopened.read(imported).project.document.profile.text.text=='New import edit'
    assert store.read(id).model_dump()==before.model_dump()


@pytest.mark.asyncio
async def test_unknown_or_corrupt_import_leaves_current_registry_globals_and_text_unchanged(tmp_path):
    store,id=await created(tmp_path);before=store.read(id);registry=store.list_projects().model_dump();rules=(store.rules.root/'rules.md').read_bytes()
    store.provider_factory=lambda:pytest.fail('invalid import inferred')
    with pytest.raises(ProjectFailure,match='ARCHIVE_SIZE_LIMIT'):await store.import_archive(b'invalid')
    assert store.read(id).model_dump()==before.model_dump() and store.list_projects().model_dump()==registry and (store.rules.root/'rules.md').read_bytes()==rules


@pytest.mark.asyncio
async def test_archive_requires_both_current_counters_and_disk_acknowledgment(tmp_path,monkeypatch):
    store,id=await created(tmp_path);before=store.read(id)
    for captured in [GuiArchiveRequest(projectRevision=1,documentRevision=2),GuiArchiveRequest(projectRevision=2,documentRevision=1)]:
        with pytest.raises(ProjectFailure,match='ARCHIVE_STALE'):await store.portable_archive(id,captured)
    monkeypatch.setattr(store,'persist',lambda _id:'failed')
    with pytest.raises(ProjectFailure,match='PROJECT_SAVE_FAILED'):await store.portable_archive(id,request(before))
    assert store.read(id).model_dump()==before.model_dump()


@pytest.mark.asyncio
async def test_legacy_import_next_rewrite_uses_global_rules_ignores_locks_and_preserves_formatting(tmp_path):
    store=service(tmp_path);provider=CreationProvider();store.provider_factory=lambda:(provider,'fixture');store.preferences=PreferencesStore(store.rules.root);store.preferences.save_analysis(False)
    imported=await store.import_archive(legacy_v3());workspace=store.read(imported);date=workspace.formatting_as_of;rules=store.rules.load()
    result=await store.rewrite(imported,rewrite_request(workspace,['profile/text'],rules=rules))
    assert result.status=='applied' and len(provider.calls)==1 and provider.calls[0]['rulesUsed']['sha256']==rules.sha256
    assert store.read(imported).formatting_as_of==date and store.read(imported).project.document.profile.text.text.startswith('Яснее:')


@pytest.mark.asyncio
async def test_imported_predraft_keeps_formatting_date_during_later_creation(tmp_path):
    store=service(tmp_path);provider=CreationProvider();store.provider_factory=lambda:(provider,'fixture')
    selected=await store.select((ROOT/'E1.txt').read_bytes(),'pasted.txt',True)
    from packages.resume_core.dates import partial_date
    store.workspaces[selected.project_id].formatting_as_of=partial_date('2020-02');store.persist(selected.project_id)
    imported=await store.import_archive(await store.portable_archive(selected.project_id,request(store.read(selected.project_id))))
    assert provider.calls==[]
    gid=store.start(imported);await asyncio.wait_for(store.tasks[(imported,gid)],40)
    assert store.read(imported).formatting_as_of==partial_date('2020-02') and provider.formatting_as_of==partial_date('2020-02')


@pytest.mark.asyncio
async def test_archive_routes_require_origin_session_strict_body_and_return_typed_new_project(tmp_path):
    provider=CreationProvider();dist=tmp_path/'dist';dist.mkdir();(dist/'index.html').write_text('Synthetic shell')
    app=create_app(secret='synthetic-project-secret-0123456789',origin='http://127.0.0.1:4317',temp_root=tmp_path/'operations',dist=dist,gui_provider=provider,data_root=tmp_path/'FoldCV')
    transport=httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport,base_url='http://127.0.0.1:4317') as client:
        files={'file':('synthetic.foldcv',legacy_v3(),'application/zip')}
        denied=await client.post('/v1/projects/archive',files=files,headers={'Origin':'http://127.0.0.1:4317'});assert denied.status_code in {401,403}
        await client.post('/v1/session/exchange',json={'secret':'synthetic-project-secret-0123456789'},headers={'Origin':'http://127.0.0.1:4317'})
        assert (await client.post('/v1/projects/archive',files=files,headers={'Origin':'https://foreign.example'})).status_code==403
        opened=await client.post('/v1/projects/archive',files=files,headers={'Origin':'http://127.0.0.1:4317'});assert opened.status_code==201
        value=opened.json();id=value['workspace']['projectId'];assert value['durability']=='durable' and provider.calls==[]
        payload={'projectRevision':value['workspace']['projectRevision'],'documentRevision':value['workspace']['documentRevision']}
        assert (await client.post('/v1/projects/'+id+'/archive',json={**payload,'extra':1},headers={'Origin':'http://127.0.0.1:4317'})).status_code==422
        download=await client.post('/v1/projects/'+id+'/archive',json=payload,headers={'Origin':'http://127.0.0.1:4317'});assert download.status_code==200 and download.headers['content-type']=='application/vnd.foldcv.project+zip'
        assert parse_json(read_zip(download.content)['manifest.json'])['schemaVersion']==5
    await app.app.state.gui_projects.shutdown()

@pytest.mark.asyncio
async def test_failed_import_disk_write_can_retry_same_identity_without_losing_current_project(tmp_path,monkeypatch):
    store,id=await created(tmp_path);before=store.read(id);data=await store.portable_archive(id,request(before));save=store.storage.save
    def failed(workspace,*args):
        if workspace.project_id!=id:raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
        return save(workspace,*args)
    monkeypatch.setattr(store.storage,'save',failed)
    imported=await store.import_archive(data);assert imported!=id and store.durability(imported)=='failed'
    assert store.read(id).model_dump()==before.model_dump() and store.read(imported).project.document==before.project.document
    monkeypatch.setattr(store.storage,'save',save);assert store.persist(imported)=='durable'
    reopened=service(tmp_path);assert reopened.read(imported).project.document==before.project.document and reopened.read(id).project.document==before.project.document

@pytest.mark.asyncio
async def test_import_interrupts_pending_operations_generation_and_analysis_without_inference(tmp_path):
    store,id=await created(tmp_path);workspace=store.workspaces[id]
    pending=store.accumulate_analysis(id,['profile/text'],['profile/text'],enable=True);assert pending.analysis_batch.enabled
    workspace.project.operations[0].status='running';workspace.generations[-1].status='running';workspace.generations[-1].stages[1].status='running'
    store.persist(id);data=await store.portable_archive(id,request(store.read(id)));store.provider_factory=lambda:pytest.fail('imported work resumed')
    imported=await store.import_archive(data);after=store.read(imported)
    assert after.generations[-1].status=='interrupted' and after.generations[-1].stages[1].status=='interrupted'
    assert after.project.operations[0].status=='interrupted' and after.project.operations[0].project_id==imported
    batch=store.pending_analysis(imported);assert batch and batch.target_field_ids==['profile/text'] and not batch.analysis_batch.enabled and batch.usage is None
    assert not any(pid==imported and not task.done() for (pid,_),task in store.tasks.items())
    reopened=service(tmp_path,CreationProvider());assert reopened.read(imported).project.document==after.project.document and reopened.provider_factory()[0].calls==[]
