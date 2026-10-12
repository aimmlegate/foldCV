"""Current DOCX cache identity, guarded downloads and real export lifecycle."""

import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
import sys
import uuid
from zipfile import ZipFile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/api/src'))

from packages.resume_core.gui_exports import GuiExportRequest
from packages.resume_core.gui_projects import GuiRenameProjectRequest
from packages.resume_core.models.recovery import record_slot
from resume_api.gui_projects import ProjectFailure
from resume_api.gui_rendering import GuiDocxRenderer
from tests.recovery.test_project_store import created, service as reopened_service, edit_request
from tests.recovery.test_gui_mutations import mutation
from tests.recovery.generation_fixtures import CreationProvider


def request(workspace, id=None):
    return GuiExportRequest(clientRequestId=id or 'export-' + str(uuid.uuid4()),
        projectRevision=workspace.project_revision, documentRevision=workspace.document_revision)


async def exported(store, id, captured=None):
    oid = store.start_export(id, captured or request(store.read(id)))
    await asyncio.wait_for(store.tasks[(id, oid)], 40)
    workspace = store.read(id)
    return workspace, next(item for item in workspace.project.operations if item.id == oid)


class CountingRenderer(GuiDocxRenderer):
    def __init__(self):
        self.calls = 0
    async def render(self, document, anchors, files):
        self.calls += 1
        return await super().render(document, anchors, files)


@pytest.mark.asyncio
async def test_current_cached_export_and_download_are_zero_call_and_make_no_render_worker(tmp_path):
    store, id = await created(tmp_path);before = store.read(id);renderer = CountingRenderer();store.renderer = renderer
    store.provider_factory = lambda: pytest.fail('export accessed content provider')
    captured = request(before);after, operation = await exported(store, id, captured)
    assert operation.status == 'completed' and operation.usage is None and renderer.calls == 0
    assert (after.project_revision, after.document_revision) == (before.project_revision, before.document_revision)
    assert after.project.document == before.project.document and after.undo_slots == before.undo_slots
    assert len(after.project.renders) == len(before.project.renders)
    content = store.export_artifact(id, operation.id);snapshot = after.project.renders[-1]
    assert hashlib.sha256(content).hexdigest() == snapshot.docx.sha256 and len(content) == snapshot.docx.size
    assert store.start_export(id, captured) == operation.id and renderer.calls == 0
    assert list((tmp_path/'operations').iterdir()) == []
    provider = CreationProvider();reopened = reopened_service(tmp_path, provider)
    assert reopened.export_artifact(id, operation.id) == content and provider.calls == []


@pytest.mark.asyncio
async def test_edited_rewritten_and_excluded_content_reaches_real_docx_without_source_refill(tmp_path):
    store, id = await created(tmp_path);workspace = store.read(id);job = workspace.project.document.jobs[0]
    from tests.recovery.test_gui_rewriting import request as rewrite_request
    from packages.resume_core.preferences import PreferencesStore
    store.preferences = PreferencesStore(store.rules.root);store.preferences.save_analysis(False)
    store.mutate(id, mutation(workspace, 'edit-field', {'fieldId':job.tasks.field_id,'text':'Подготовила инструкцию для дежурной смены.',
        'periods':None,'focus':None,'sessionId':'tasks','completion':'slot'}))
    workspace = store.read(id)
    await store.rewrite(id, rewrite_request(workspace, [job.tasks.field_id], rules=store.rules.load()))
    workspace = store.read(id);removed = workspace.project.document.jobs[1]
    store.mutate(id, mutation(workspace, 'delete', {'sectionId':'jobs','recordId':removed.id}))
    workspace = store.read(id)
    store.mutate(id, mutation(workspace, 'hide', {'slotId':'profile','visible':False}))
    renderer = CountingRenderer();store.renderer = renderer;store.provider_factory = lambda: pytest.fail('export inferred')
    after, operation = await exported(store, id)
    assert operation.status == 'completed' and renderer.calls == 1
    with ZipFile(BytesIO(store.export_artifact(id, operation.id))) as archive:
        xml = archive.read('word/document.xml').decode()
        assert 'Яснее: Подготовила инструкцию для дежурной смены.' in xml
        assert 'Интеграционные тесты.' not in xml and removed.employer.text not in xml
        assert 'Разрабатываю backend-сервисы на Python.' not in xml and 'mail@example.com' not in xml
        assert 'Уточните' not in xml and 'editorial_plan_stale' not in xml
        assert 'word/styles.xml' in archive.namelist()
    assert len([item for item in after.project.operations if item.kind in {'normalize_semantics','draft_prose','rewrite_prose','reconcile_edits'} and (item.kind != 'reconcile_edits' or item.analysis_batch.phase == 'dispatched')]) == 3
    assert after.undo_slots[record_slot(job)] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['text', 'rename', 'renderer', 'template', 'hash', 'missing'])
async def test_stale_cached_download_cannot_return_old_bytes_after_dependency_change(tmp_path, monkeypatch, change):
    store, id = await created(tmp_path);workspace, operation = await exported(store, id)
    snapshot = next(item for item in workspace.project.renders if item.id == operation.render_snapshot_id)
    if change == 'text':
        store.mutate(id, edit_request(workspace, 'New authored text'))
    elif change == 'rename':
        store.rename(id, GuiRenameProjectRequest(title='Renamed', baseRevision=workspace.project_revision))
    elif change == 'renderer':
        monkeypatch.setattr('resume_api.gui_exports.renderer_sha256', lambda: '0'*64)
    elif change == 'template':
        next(item for item in store.workspaces[id].project.renders if item.id == snapshot.id).template_sha256 = '0'*64
    elif change == 'hash':
        store.artifacts[(id, snapshot.id)] = b'corrupted cache'
    else:
        store.artifacts.pop((id, snapshot.id))
    with pytest.raises(ProjectFailure, match='EXPORT_STALE'):
        store.export_artifact(id, operation.id)


class DelayedRenderer(GuiDocxRenderer):
    def __init__(self):
        self.started, self.release = asyncio.Event(), asyncio.Event()
    async def render(self, document, anchors, files):
        self.started.set();await self.release.wait()
        return await super().render(document, anchors, files)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['text', 'rename', 'cancel'])
async def test_export_while_editing_rejects_late_worker_result_without_losing_text_or_pointer(tmp_path, change):
    store, id = await created(tmp_path);store.mutate(id, edit_request(store.read(id), 'Current input', completion='slot'))
    renderer = DelayedRenderer();store.renderer = renderer
    oid = store.start_export(id, request(store.read(id)));await asyncio.wait_for(renderer.started.wait(), 5)
    if change == 'text':store.mutate(id, edit_request(store.read(id), 'Newer input', completion='none'))
    elif change == 'rename':store.rename(id, GuiRenameProjectRequest(title='New title', baseRevision=store.read(id).project_revision))
    else:store.cancels[(id, oid)].set()
    before = store.read(id);renderer.release.set();await asyncio.wait_for(store.tasks[(id, oid)], 40)
    after = store.read(id);operation = next(item for item in after.project.operations if item.id == oid)
    assert operation.status == ('cancelled' if change == 'cancel' else 'failed')
    assert operation.error_code == ('CANCELLED' if change == 'cancel' else 'EXPORT_STALE')
    assert after.project.document == before.project.document and after.undo_slots == before.undo_slots and after.edit_sessions == before.edit_sessions
    assert after.project.renders == before.project.renders and list((tmp_path/'operations').iterdir()) == []


@pytest.mark.asyncio
async def test_capacity_error_retains_safe_field_identity_and_retry_uses_current_text(tmp_path, capsys):
    store, id = await created(tmp_path);workspace = store.read(id);job = workspace.project.document.jobs[0]
    store.mutate(id, mutation(workspace, 'edit-field', {'fieldId':job.context.field_id,'text':'x'*4001,
        'periods':None,'focus':None,'sessionId':'context','completion':'none'}))
    renderer = CountingRenderer();store.renderer = renderer
    workspace, operation = await exported(store, id)
    assert operation.status == 'failed' and operation.docx_error.code == 'DOCX_TEXT_LIMIT'
    assert operation.docx_error.path == 'projects[0].description' and operation.docx_error.anchor.field_id == job.context.field_id
    assert renderer.calls == 0 and workspace.project.document.jobs[0].context.text == 'x'*4001
    assert 'xxxx' not in operation.model_dump_json() and capsys.readouterr() == ('','')
    store.mutate(id, mutation(workspace, 'edit-field', {'fieldId':job.context.field_id,'text':'Short current context.',
        'periods':None,'focus':None,'sessionId':'context','completion':'none'}))
    after, retry = await exported(store, id)
    assert retry.status == 'completed' and renderer.calls == 1
    assert after.project.document.jobs[0].context.text == 'Short current context.'


@pytest.mark.asyncio
async def test_export_requires_current_durable_input_but_not_a_ready_model(tmp_path, monkeypatch):
    store, id = await created(tmp_path);store.provider_factory = lambda: None
    store.mutate(id, edit_request(store.read(id), 'Offline current text'))
    workspace, operation = await exported(store, id);assert operation.status == 'completed'
    stale = request(workspace);stale.document_revision -= 1
    with pytest.raises(ProjectFailure, match='EXPORT_STALE'):store.start_export(id, stale)
    from packages.resume_core.project_store import ProjectStoreFailure
    def denied(*_args):raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
    monkeypatch.setattr(store.storage,'save',denied)
    with pytest.raises(ProjectFailure, match='PROJECT_SAVE_FAILED'):store.start_export(id, request(store.read(id)))


@pytest.mark.asyncio
async def test_pending_semantic_operation_does_not_block_export_of_current_document(tmp_path):
    store, id = await created(tmp_path)
    workspace = store.workspaces[id]
    workspace.project.operations.append(workspace.project.operations[0].model_copy(update={
        'id':'pending-semantic','kind':'reconcile_edits','status':'queued','usage':None,'events':[]},deep=True))
    pending = asyncio.create_task(asyncio.sleep(.2));store.tasks[(id,'pending-semantic')] = pending
    workspace, operation = await exported(store, id)
    assert operation.status == 'completed' and workspace.project.document is not None
    await pending


@pytest.mark.asyncio
async def test_structural_corruption_and_predraft_export_fail_visibly_without_worker(tmp_path):
    store, id = await created(tmp_path);workspace = store.workspaces[id]
    workspace.project.document.jobs[0].id = workspace.project.document.candidate.id
    with pytest.raises(ProjectFailure, match='EXPORT_INVALID_DOCUMENT'):store.start_export(id, request(workspace))
    with pytest.raises(ProjectFailure, match='EXPORT_INVALID_DOCUMENT'):store.export_artifact(id, 'unknown')
    other = store.allocate('PreDraft')
    with pytest.raises(ProjectFailure, match='DOCUMENT_UNAVAILABLE'):store.start_export(other, request(store.read(other)))
    with pytest.raises(ProjectFailure, match='EXPORT_UNAVAILABLE'):store.export_artifact(other, 'unknown')
    assert list((tmp_path/'operations').iterdir()) == []


@pytest.mark.asyncio
async def test_cached_export_still_validates_repository_assets(tmp_path, monkeypatch):
    from packages.resume_core.rendering.template import RenderFailure
    store, id = await created(tmp_path);renderer = CountingRenderer();store.renderer = renderer
    def unavailable():raise RenderFailure('TEMPLATE_MISMATCH')
    monkeypatch.setattr('resume_api.gui_exports.require_docx_template', unavailable)
    workspace, operation = await exported(store, id)
    assert operation.status == 'failed' and operation.docx_error.code == 'DOCX_RENDER_FAILED' and renderer.calls == 0
    assert workspace.project.document is not None
