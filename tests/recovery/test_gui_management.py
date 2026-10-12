"""Isolated registry metadata, durable tombstones and verified project cleanup."""

import asyncio
from pathlib import Path
import sys
import json

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'services/api/src'))
from packages.resume_core.gui_projects import GuiRenameProjectRequest
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.preferences import PreferencesStore
from resume_api.gui_projects import ProjectFailure
from tests.recovery.test_project_store import created,service as durable_service
from tests.recovery.test_gui_projects import finish
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.test_gui_reconciliation import AnalysisProvider,change,started,settled
from tests.recovery.candidate_fixtures import ROOT


async def pair(tmp_path):
    store,first=await created(tmp_path);provider=CreationProvider('E2');store.provider_factory=lambda:(provider,'fixture')
    selected=await store.select((ROOT/'E2.txt').read_bytes(),'pasted.txt',True)
    await finish(store,selected.project_id,store.start(selected.project_id))
    return store,first,selected.project_id


@pytest.mark.asyncio
async def test_registry_reads_two_isolated_projects_and_manual_title_survives_restart(tmp_path):
    store,first,second=await pair(tmp_path);before=store.read(first)
    store.provider_factory=lambda:pytest.fail('list/rename inferred')
    store.rename(first,GuiRenameProjectRequest(title='Manual project name',baseRevision=before.project_revision))
    after=store.read(first);assert (after.project_revision,after.document_revision)==(before.project_revision+1,before.document_revision)
    assert after.project.document==before.project.document and after.title_manually_set
    rows=store.list_projects();assert {row.project_id for row in rows.entries}=={first,second}
    provider=CreationProvider();reopened=durable_service(tmp_path,provider)
    assert reopened.read(first).title=='Manual project name' and reopened.read(second).project.document!=after.project.document
    assert provider.calls==[] and len(reopened.list_projects().entries)==2


@pytest.mark.asyncio
async def test_manual_predraft_title_survives_creation_and_keeps_default_document_name(tmp_path):
    store=durable_service(tmp_path);selected=await store.select((ROOT/'E1.txt').read_bytes(),'pasted.txt',True)
    store.rename(selected.project_id,GuiRenameProjectRequest(title='Manual before creation',baseRevision=1))
    after=await finish(store,selected.project_id,store.start(selected.project_id))
    assert after.title=='Manual before creation' and after.title_manually_set and after.project.document.candidate.name.text!='Manual before creation'
    assert (after.project_revision,after.document_revision)==(3,2)


@pytest.mark.asyncio
async def test_deletion_removes_only_verified_project_and_never_resurrects_late_snapshots(tmp_path):
    store,first,second=await pair(tmp_path);old=store.read(first);other=store.read(second)
    export=tmp_path/'download.docx';export.write_bytes(next(content for (id,_),content in store.artifacts.items() if id==first));expected=export.read_bytes()
    profile=store.storage.root/'cli-experiment';profile.mkdir();(profile/'retained-state').write_bytes(b'private fixture')
    rules=(store.storage.root/'rules.md').read_bytes();PreferencesStore(store.storage.root).save_analysis(False);prefs=(store.storage.root/'preferences.json').read_bytes()
    result=await store.delete_project(first);assert result.status=='deleted'
    assert not (store.storage.projects/first).exists() and (store.storage.projects/second).exists()
    assert export.read_bytes()==expected and (profile/'retained-state').read_bytes()==b'private fixture'
    assert (store.storage.root/'rules.md').read_bytes()==rules and (store.storage.root/'preferences.json').read_bytes()==prefs
    assert store.read(second).model_dump()==other.model_dump() and len(store.list_projects().entries)==1
    with pytest.raises(ProjectFailure,match='PROJECT_DELETED'):store.read(first)
    assert store.persist(first)=='failed'
    with pytest.raises(ProjectStoreFailure,match='PROJECT_DELETED'):store.storage.save(old,store.originals,store.artifacts)
    reopened=durable_service(tmp_path);assert [row.project_id for row in reopened.list_projects().entries]==[second]
    with pytest.raises(ProjectFailure,match='PROJECT_DELETED'):reopened.read(first)
    assert not (store.storage.projects/first).exists()


@pytest.mark.asyncio
async def test_tombstone_write_failure_removes_nothing_and_keeps_project_editable(tmp_path,monkeypatch):
    store,id=await created(tmp_path);before=store.read(id);paths={path.relative_to(store.storage.projects/id):path.read_bytes() for path in (store.storage.projects/id).rglob('*') if path.is_file()}
    def failed(*args):raise OSError('controlled registry failure')
    monkeypatch.setattr(store.storage,'_write_registry',failed)
    with pytest.raises(ProjectFailure,match='PROJECT_DELETE_FAILED'):await store.delete_project(id)
    assert id not in store.deleted_ids and store.read(id).model_dump()==before.model_dump()
    assert {path.relative_to(store.storage.projects/id):path.read_bytes() for path in (store.storage.projects/id).rglob('*') if path.is_file()}==paths


@pytest.mark.asyncio
async def test_file_cleanup_failure_keeps_tombstone_allows_retry_and_does_not_block_other_projects(tmp_path,monkeypatch):
    store,first,second=await pair(tmp_path);original=Path.unlink
    def fail(path,*args,**kwargs):
        if path==store.storage.projects/first/'workspace.json':raise OSError('controlled removal failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',fail)
    result=await store.delete_project(first);assert result.status=='cleanup_incomplete' and result.error_code=='PROJECT_CLEANUP_FAILED'
    assert not store.analysis_cleanup_failed and store.storage.registry().entries[0].tombstoned
    other=store.read(second);store.rename(second,GuiRenameProjectRequest(title='Other remains available',baseRevision=other.project_revision))
    with pytest.raises(ProjectFailure,match='PROJECT_DELETED'):store.read(first)
    monkeypatch.setattr(Path,'unlink',original)
    assert (await store.delete_project(first)).status=='deleted' and store.read(second).title=='Other remains available'


@pytest.mark.asyncio
@pytest.mark.parametrize('unsafe',['unknown_file','symlink','hardlink','unverified_identity'])
async def test_cleanup_rejects_unowned_files_links_or_identity_without_touching_exports(tmp_path,unsafe):
    store,id=await created(tmp_path);directory=store.storage.projects/id
    outside=tmp_path/'user-export.docx';outside.write_bytes(b'retain exported bytes');outside.chmod(0o600)
    if unsafe=='unknown_file':(directory/'user-export.docx').write_bytes(b'unrelated')
    elif unsafe in {'symlink','hardlink'}:
        source=next((directory/'sources').iterdir());source.unlink()
        if unsafe=='symlink':source.symlink_to(outside)
        else:
            import os;os.link(outside,source)
    else:(directory/'.project-identity.json').write_text(json.dumps({'version':1,'projectId':'foreign'}))
    if unsafe=='unverified_identity':
        with pytest.raises(ProjectFailure,match='PROJECT_DELETE_FAILED'):await store.delete_project(id)
    else:assert (await store.delete_project(id)).status=='cleanup_incomplete'
    assert outside.read_bytes()==b'retain exported bytes' and directory.exists() and (directory/'workspace.json').exists()
    assert not store.analysis_cleanup_failed


@pytest.mark.asyncio
async def test_delete_during_reconciliation_tombstones_before_cleanup_and_rejects_late_reply(tmp_path):
    store,id=await created(tmp_path);provider=AnalysisProvider(delayed=True);store.provider_factory=lambda:(provider,'fixture');store.analysis_delay=.01
    workspace=store.workspaces[id];change(store,workspace,'Completed change',completion='field');await started(provider)
    deleting=asyncio.create_task(store.delete_project(id))
    async def marked():
        while id not in store.deleted_ids:await asyncio.sleep(.005)
    await asyncio.wait_for(marked(),5)
    with pytest.raises(ProjectFailure,match='PROJECT_DELETED'):store.read(id)
    assert (store.storage.projects/id).exists() and not deleting.done()
    provider.release.set();assert (await deleting).status=='deleted'
    await asyncio.sleep(.05);assert not (store.storage.projects/id).exists() and len(provider.calls)==1
    assert list((tmp_path/'operations').iterdir())==[]


@pytest.mark.asyncio
async def test_delete_during_owned_input_extraction_stops_request_and_preserves_other_project(tmp_path,monkeypatch):
    import resume_api.gui_projects as module
    store,other=await created(tmp_path);entered=asyncio.Event();release=asyncio.Event();original=module.run_extract
    async def delayed(*args):
        result=await original(*args);entered.set();await release.wait();return result
    monkeypatch.setattr(module,'run_extract',delayed)
    selecting=asyncio.create_task(store.select((ROOT/'E2.txt').read_bytes(),'pasted.txt',True));await entered.wait()
    id=next(id for id in store.workspaces if id!=other);assert any(key[0]==id for key in store.input_tasks)
    deleting=asyncio.create_task(store.delete_project(id));await asyncio.sleep(.02);release.set()
    assert (await deleting).status=='deleted'
    with pytest.raises(ProjectFailure,match='PROJECT_DELETED'):await selecting
    assert store.read(other).project and not store.input_tasks and not (store.storage.projects/id).exists()


@pytest.mark.asyncio
async def test_protected_list_and_delete_require_literal_confirmation_and_keep_zero_calls(tmp_path):
    from tests.recovery.test_preferences import application,MetadataAdapter,client_session
    provider=CreationProvider();app=application(tmp_path,MetadataAdapter(),provider);store=app.app.state.gui_projects
    selected=await store.select((ROOT/'E1.txt').read_bytes(),'pasted.txt',True);id=selected.project_id
    async with client_session(app) as client:
        listed=await client.get('/v1/projects');assert listed.status_code==200 and listed.json()['entries'][0]['projectId']==id
        assert (await client.get('/v1/projects?private=invalid')).status_code==403
        for value in [False,1,'true',None]:
            denied=await client.request('DELETE','/v1/projects/'+id,json={'confirmed':value});assert denied.status_code==422
        assert (await client.request('DELETE','/v1/projects/'+id,headers={'Origin':'http://foreign.invalid'},json={'confirmed':True})).status_code==403
        assert (await client.request('DELETE','/v1/projects/'+id,content=b'{"confirmed":true,"confirmed":false}',headers={'Content-Type':'application/json'})).status_code==422
        result=await client.request('DELETE','/v1/projects/'+id,json={'confirmed':True});assert result.status_code==200 and result.json()['status']=='deleted'
        assert (await client.get('/v1/projects/'+id)).status_code==410 and (await client.get('/v1/projects')).json()['entries']==[]
        assert provider.calls==[]


@pytest.mark.asyncio
async def test_delete_cancels_queued_generation_without_admission_or_model_call(tmp_path):
    from resume_api.gui_admission import AdmissionCancelled
    class Queued(CreationProvider):
        def __init__(self):super().__init__();self.waiting=__import__('threading').Event()
        def generate_queued(self,request,files,cancel,admitted):
            self.waiting.set()
            while not cancel.wait(.01):pass
            raise AdmissionCancelled()
    provider=Queued();store=durable_service(tmp_path,provider)
    selected=await store.select((ROOT/'E1.txt').read_bytes(),'pasted.txt',True);id=selected.project_id;gid=store.start(id)
    async def waiting():
        while not provider.waiting.is_set():await asyncio.sleep(.005)
    await asyncio.wait_for(waiting(),5);workspace=store.workspaces[id]
    assert (await store.delete_project(id)).status=='deleted' and provider.calls==[]
    assert workspace.generations[-1].status=='cancelled' and workspace.pre_draft.operations[0].usage.logical_attempts==0


@pytest.mark.asyncio
async def test_delete_cancels_input_waiting_for_worker_slot_without_starting_extraction(tmp_path):
    from contextlib import asynccontextmanager
    from resume_api.gui_admission import AdmissionCancelled
    store=durable_service(tmp_path);entered=asyncio.Event()
    @asynccontextmanager
    async def queued(cancel):
        entered.set()
        while not cancel.is_set():await asyncio.sleep(.005)
        raise AdmissionCancelled()
        yield
    store.worker_slot=queued
    selecting=asyncio.create_task(store.select((ROOT/'E1.txt').read_bytes(),'pasted.txt',True));await entered.wait();id=next(iter(store.workspaces))
    assert (await store.delete_project(id)).status=='deleted'
    with pytest.raises(ProjectFailure,match='PROJECT_DELETED'):await selecting
    assert not store.input_tasks and not (store.storage.projects/id).exists()
