"""Explicit retries reuse only available matching outputs and preserve committed work."""

from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'services/api/src'))
import pytest
from packages.resume_core.gui_projects import GuiRenameProjectRequest
from packages.resume_core.rendering.docx_errors import failure
from resume_api.gui_projects import ProjectFailure
from resume_api.gui_rendering import GuiDocxRenderer
from tests.recovery.test_project_store import service
from tests.recovery.test_gui_projects import finish
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.candidate_fixtures import ROOT


async def failed_draft(tmp_path):
    provider=CreationProvider(fail_kind='GuiDraftProposal');store=service(tmp_path,provider)
    selected=await store.select((ROOT/'E1.txt').read_bytes(),'pasted.txt',True)
    failed=await finish(store,selected.project_id,store.start(selected.project_id))
    assert failed.generations[-1].status=='failed' and failed.generations[-1].stages[1].status=='completed'
    return store,provider,failed


@pytest.mark.asyncio
async def test_restart_never_resumes_and_explicit_retry_rebuilds_unavailable_normalized_output(tmp_path):
    store,_,failed=await failed_draft(tmp_path);provider=CreationProvider();reopened=service(tmp_path,provider);before=reopened.read(failed.project_id)
    assert provider.calls==[] and before.pre_draft.facts and before.generations[-1].status=='failed'
    completed=await finish(reopened,failed.project_id,reopened.start(failed.project_id,before.generations[-1].id))
    assert completed.generations[-1].status=='completed' and len(provider.calls)==2
    assert completed.project.document.candidate.name.text=='Ирина Примерова'


@pytest.mark.asyncio
async def test_retry_uses_current_selected_source_and_preserves_all_originals_after_failed_draft(tmp_path):
    store,provider,failed=await failed_draft(tmp_path);id=failed.project_id;old=failed.generations[-1]
    provider.example='E2';provider.fail_kind=None
    selected=await store.select((ROOT/'E2.txt').read_bytes(),'replacement.txt',False,id)
    completed=await finish(store,id,store.start(id,old.id))
    assert completed.generations[-1].source_ids==[selected.pre_draft.selected_source_id]
    assert completed.project.document.candidate.name.text=='Алексей' and len(provider.calls)==4
    assert len(completed.project.sources)==2 and {ref for source in completed.project.sources for unit in source.units for ref in unit.represented_fact_ids}<={fact.id for fact in completed.project.facts}
    assert {value for (pid,_),value in store.originals.items() if pid==id}=={(ROOT/'E1.txt').read_bytes(),(ROOT/'E2.txt').read_bytes()}


@pytest.mark.asyncio
async def test_retry_with_failed_replacement_never_uses_old_usable_source(tmp_path):
    store,provider,failed=await failed_draft(tmp_path)
    await store.select(b'broken PDF','broken.pdf',False,failed.project_id)
    with pytest.raises(ProjectFailure,match='NO_USABLE_TEXT'):store.start(failed.project_id,failed.generations[-1].id)
    assert len(provider.calls)==2


@pytest.mark.asyncio
async def test_same_markdown_hash_with_new_revision_invalidates_old_stage_context(tmp_path):
    store,provider,failed=await failed_draft(tmp_path);original=store.rules.load()
    intermediate=store.rules.save(original.markdown+'\nTemporary policy',original.revision)
    current=store.rules.save(original.markdown,intermediate.revision);assert current.sha256==original.sha256 and current.revision==3
    provider.fail_kind=None;completed=await finish(store,failed.project_id,store.start(failed.project_id,failed.generations[-1].id))
    assert len(provider.calls)==4 and completed.editorial_plan.rules_revision==3
    assert all(call['rulesUsed']['revision']==3 for call in provider.calls[-2:])


class BrokenRenderer:
    async def render(self,*_args):raise failure('DOCX_BLOCK_PAGE_BUDGET')


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['restart','rename','rules'])
async def test_render_retry_keeps_committed_document_and_facts_without_content_calls(tmp_path,change):
    provider=CreationProvider();store=service(tmp_path,provider);store.renderer=BrokenRenderer()
    selected=await store.select((ROOT/'E1.txt').read_bytes(),'pasted.txt',True);id=selected.project_id
    failed=await finish(store,id,store.start(id));assert failed.project is not None and failed.generations[-1].status=='failed'
    if change=='restart':store=service(tmp_path,provider)
    elif change=='rename':store.rename(id,GuiRenameProjectRequest(title='Manual title',baseRevision=failed.project_revision))
    else:
        rules=store.rules.load();store.rules.save(rules.markdown+'\nNew policy',rules.revision)
    before=store.read(id);store.provider_factory=lambda:pytest.fail('render retry inferred');store.renderer=GuiDocxRenderer()
    completed=await finish(store,id,store.start(id,failed.generations[-1].id))
    assert completed.generations[-1].status=='completed' and len(provider.calls)==2
    assert completed.project.document==before.project.document and completed.project.facts==before.project.facts and completed.undo_slots==before.undo_slots
    assert (completed.project_revision,completed.document_revision)==(before.project_revision,before.document_revision)


@pytest.mark.asyncio
async def test_corrupt_cached_output_cannot_masquerade_as_completed_matching_stage(tmp_path):
    store,provider,failed=await failed_draft(tmp_path);key=(failed.project_id,failed.generations[-1].id)
    result=store.cache[key]['normalized'].model_copy(deep=True);result.rules_revision+=1;store.cache[key]['normalized']=result
    provider.fail_kind=None;completed=await finish(store,failed.project_id,store.start(failed.project_id,failed.generations[-1].id))
    assert completed.generations[-1].status=='completed' and len(provider.calls)==4
    assert completed.editorial_plan.rules_revision==store.rules.load().revision


@pytest.mark.asyncio
async def test_preflight_failure_returns_saved_identity_and_same_paste_retry_does_not_duplicate_project_or_source(tmp_path):
    import httpx
    from resume_api.app import create_app
    from tests.recovery.generation_fixtures import frozen_now
    origin='http://127.0.0.1:4319';secret='synthetic-recovery-secret-0123456789';dist=tmp_path/'dist';dist.mkdir();(dist/'index.html').write_text('Synthetic shell')
    app=create_app(origin=origin,secret=secret,temp_root=tmp_path/'operations',dist=dist,data_root=tmp_path/'FoldCV',gui_clock=frozen_now)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=origin) as client:
        headers={'Origin':origin};await client.post('/v1/session/exchange',headers=headers,json={'secret':secret})
        raw=(ROOT/'E1.txt').read_text();blocked=await client.post('/v1/projects',headers=headers,json={'text':raw})
        assert blocked.status_code==409 and blocked.json()['error']['code']=='CONNECTION_REQUIRED'
        id=blocked.headers['X-FoldCV-Project-Id'];saved=(await client.get('/v1/projects/'+id)).json();assert saved['durability']=='durable' and saved['workspace']['preDraft']['extractedText']==raw
        provider=CreationProvider();store=app.app.state.gui_projects;store.provider_factory=lambda:(provider,'fixture')
        started=await client.post('/v1/projects/'+id+'/generations',headers=headers,json={'text':raw});assert started.status_code==202
        await finish(store,id,started.json()['generationId']);assert len(store.list_projects().entries)==1 and len(store.read(id).project.sources)==1 and len(provider.calls)==2
    await app.app.state.gui_projects.shutdown()


@pytest.mark.asyncio
async def test_corrupt_rules_failure_preserves_input_identity_and_starts_no_content(tmp_path):
    provider=CreationProvider();store=service(tmp_path,provider);selected=await store.select((ROOT/'E1.txt').read_bytes(),'pasted.txt',True)
    store.rules.load();store.rules.path.write_text(store.rules.path.read_text().replace('15 years','20 years'))
    with pytest.raises(ProjectFailure,match='RULES_LOAD_FAILED'):store.start(selected.project_id)
    assert store.read(selected.project_id).pre_draft.extracted_text==(ROOT/'E1.txt').read_text()
    assert provider.calls==[] and store.read(selected.project_id).generations==[] and store.durability(selected.project_id)=='durable'
