"""Private durable snapshots, restart recovery and failed acknowledgment boundaries."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/api/src'))

from packages.resume_core import project_store as storage_module
from packages.resume_core.project_store import ProjectStore, ProjectStoreFailure
from packages.resume_core.rules import RulesStore
from packages.resume_core.storage import atomic_write
from resume_api.gui_projects import GuiProjectService, ProjectFailure
from resume_api.providers.content import ContentFailure
from tests.recovery.candidate_fixtures import ROOT
from tests.recovery.generation_fixtures import CreationProvider, frozen_now
from tests.recovery.test_gui_projects import finish
from tests.recovery.test_gui_mutations import mutation


def service(tmp_path, provider=None):
    root = tmp_path / 'FoldCV'
    return GuiProjectService(tmp_path / 'operations', RulesStore(root), lambda: (provider or CreationProvider(), 'fixture'),
        clock=frozen_now, storage=ProjectStore(root))


async def created(tmp_path):
    store = service(tmp_path)
    selected = await store.select((ROOT / 'E1.txt').read_bytes(), 'pasted.txt', True)
    await finish(store, selected.project_id, store.start(selected.project_id))
    return store, selected.project_id


def edit_request(workspace, text, session='session', completion='none', id=None):
    return mutation(workspace, 'edit-field', {'fieldId': 'profile/text', 'text': text, 'periods': None, 'focus': None,
        'sessionId': session, 'completion': completion}, id=id)


@pytest.mark.asyncio
async def test_settled_restart_preserves_full_snapshot_originals_artifacts_and_private_permissions(tmp_path):
    store, id = await created(tmp_path)
    before = store.read(id)
    provider = CreationProvider()
    reopened = service(tmp_path, provider)
    after = reopened.read(id)
    assert after.model_dump() == before.model_dump() and provider.calls == []
    assert reopened.originals == store.originals and reopened.artifacts == store.artifacts
    assert reopened.durability(id) == 'durable' and (after.project_revision, after.document_revision) == (2, 2)
    assert reopened.saved_revisions[id] == (2, 2)
    for path in (tmp_path / 'FoldCV').rglob('*'):
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
    assert stat.S_IMODE((tmp_path / 'FoldCV').stat().st_mode) == 0o700
    raw = json.loads((tmp_path / 'FoldCV/projects' / id / 'workspace.json').read_text())
    assert raw['schemaVersion'] == 5 and raw['project']['schemaVersion'] == 4


@pytest.mark.asyncio
async def test_restart_retains_open_session_two_step_restore_and_consumed_pointer(tmp_path):
    store, id = await created(tmp_path)
    original = store.read(id).project.document.profile.text.text
    assert store.mutate(id, edit_request(store.read(id), 'First', completion='slot')).persistence == 'durable'
    assert store.mutate(id, edit_request(store.read(id), 'Unfinished', session='second')).persistence == 'durable'
    reopened = service(tmp_path)
    workspace = reopened.read(id)
    assert workspace.edit_sessions['profile'].session_id == 'second'
    assert workspace.edit_sessions['profile'].baseline.record.text.text == 'First'
    assert workspace.undo_slots['profile'].record.text.text == original
    for expected in ['First', original]:
        result = reopened.mutate(id, mutation(reopened.read(id), 'restore-previous-block', {'slotId': 'profile', 'sessionId': 'second'}))
        assert result.persistence == 'durable' and reopened.read(id).project.document.profile.text.text == expected
    again = service(tmp_path)
    restored = again.read(id)
    assert restored.undo_slots['profile'] is None
    assert restored.edit_sessions['profile'].baseline.record.text.text == original
    before = (restored.project_revision, restored.document_revision)
    again.mutate(id, edit_request(restored, original, session='second', completion='slot'))
    assert (again.read(id).project_revision, again.read(id).document_revision) == before
    assert again.read(id).undo_slots['profile'] is None


@pytest.mark.asyncio
async def test_mutation_replay_is_durable_slim_and_payload_reuse_rejects_after_restart(tmp_path):
    store, id = await created(tmp_path)
    request = edit_request(store.read(id), 'Retained', completion='slot', id='durable-id')
    applied = store.mutate(id, request)
    reopened = service(tmp_path)
    replay = reopened.mutate(id, request)
    assert replay.status == 'replayed' and replay.persistence == 'durable'
    assert (replay.project_revision, replay.document_revision) == (applied.project_revision, applied.document_revision)
    changed = request.model_copy(deep=True);changed.root.payload.text = 'Different'
    assert reopened.mutate(id, changed).rejection_reason == 'MUTATION_ID_REUSED'
    records = reopened.read(id).mutation_replay
    assert len(records) == 1 and 'text' not in records[0].model_dump()


@pytest.mark.asyncio
async def test_write_failure_keeps_memory_and_previous_disk_ack_then_exact_retry_saves_once(tmp_path, monkeypatch):
    store, id = await created(tmp_path)
    before = store.read(id)
    write = storage_module.atomic_write
    fail = True
    def failing(path, data):
        if fail and path.name == 'workspace.json':raise OSError('synthetic disk failure')
        write(path, data)
    monkeypatch.setattr(storage_module, 'atomic_write', failing)
    request = edit_request(before, 'Unacknowledged text', completion='slot', id='retry-id')
    result = store.mutate(id, request)
    assert result.status == 'applied' and result.persistence == 'failed' and store.durability(id) == 'failed'
    assert store.read(id).project.document.profile.text.text == 'Unacknowledged text'
    disk = json.loads((tmp_path / 'FoldCV/projects' / id / 'workspace.json').read_text())
    assert disk['documentRevision'] == 2 and store.saved_revisions[id] == (2, 2)
    fail = False
    retried = store.mutate(id, request)
    assert retried.status == 'replayed' and retried.persistence == 'durable'
    assert (retried.project_revision, retried.document_revision) == (3, 3)
    assert service(tmp_path).read(id).project.document.profile.text.text == 'Unacknowledged text'


@pytest.mark.asyncio
async def test_failed_original_save_retains_selected_input_and_blocks_inference_until_retry(tmp_path, monkeypatch):
    provider = CreationProvider();store = service(tmp_path, provider)
    write = storage_module.atomic_write
    fail = True
    def failing(path, data):
        if fail and path.suffix == '.bin':raise OSError('synthetic original failure')
        write(path, data)
    monkeypatch.setattr(storage_module, 'atomic_write', failing)
    data = (ROOT / 'E1.txt').read_bytes()
    selected = await store.select(data, 'source.txt', False)
    id = selected.project_id
    assert selected.pre_draft.selected_input == 'file' and selected.pre_draft.extracted_text.strip()
    assert store.durability(id) == 'failed' and provider.calls == []
    assert store.originals[(id, selected.pre_draft.selected_source_id)] == data
    with pytest.raises(ProjectFailure, match='PROJECT_SAVE_FAILED'):store.start(id)
    fail = False
    assert store.persist(id) == 'durable'
    result = await finish(store, id, store.start(id))
    assert result.generations[-1].status == 'completed' and len(provider.calls) == 2


@pytest.mark.asyncio
async def test_failed_extraction_warnings_and_exact_original_survive_precreation_restart(tmp_path):
    provider = CreationProvider();store = service(tmp_path, provider)
    selected = await store.select(b'broken PDF bytes', 'broken.pdf', False)
    id, source_id = selected.project_id, selected.pre_draft.selected_source_id
    reopened = service(tmp_path, provider);workspace = reopened.read(id)
    assert workspace.pre_draft.warnings == selected.pre_draft.warnings
    assert workspace.pre_draft.selected_input == 'file' and workspace.pre_draft.extracted_text == ''
    assert reopened.originals[(id, source_id)] == b'broken PDF bytes'
    with pytest.raises(ProjectFailure, match='NO_USABLE_TEXT'):reopened.start(id)
    assert provider.calls == []


@pytest.mark.asyncio
async def test_pending_work_reopens_interrupted_with_admitted_count_and_zero_new_calls(tmp_path):
    entered = threading.Event()
    class Waiting(CreationProvider):
        def generate_queued(self, request, files, cancel, admitted):
            admitted();entered.set();cancel.wait(10)
            raise ContentFailure('CANCELLED', logical_attempts=1)
    waiting = Waiting();store = service(tmp_path, waiting)
    selected = await store.select((ROOT / 'E1.txt').read_bytes(), 'pasted.txt', True)
    id, gid = selected.project_id, store.start(selected.project_id)
    assert await asyncio.to_thread(entered.wait, 3)
    provider = CreationProvider();reopened = service(tmp_path, provider);workspace = reopened.read(id)
    assert workspace.generations[-1].status == 'interrupted'
    assert workspace.pre_draft.operations[-1].status == 'interrupted'
    assert workspace.pre_draft.operations[-1].usage.logical_attempts == 1
    assert provider.calls == [] and (workspace.project_revision, workspace.document_revision) == (1, 1)
    await store.cancel(id, gid)
    assert service(tmp_path).read(id).generations[-1].status == 'interrupted'


@pytest.mark.asyncio
async def test_original_is_durable_before_extraction_and_interrupted_file_does_not_fall_back(tmp_path, monkeypatch):
    import resume_api.gui_projects as module
    entered = asyncio.Event()
    async def pending(*_args):entered.set();await asyncio.Event().wait()
    monkeypatch.setattr(module, 'run_extract', pending)
    store = service(tmp_path);data = b'controlled pending file'
    task = asyncio.create_task(store.select(data, 'source.txt', False))
    await asyncio.wait_for(entered.wait(), 2)
    id = next(iter(store.workspaces))
    workspace = service(tmp_path).read(id)
    assert workspace.pre_draft.selected_input == 'file' and workspace.pre_draft.extracted_text == ''
    assert workspace.pre_draft.warnings == ['EXTRACT_INTERRUPTED', 'NO_USABLE_TEXT']
    loaded, _, _ = ProjectStore(tmp_path / 'FoldCV').load_all()
    assert next(iter(loaded[id][1].values())) == data
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task


@pytest.mark.asyncio
async def test_two_store_instances_cannot_overwrite_newer_committed_text(tmp_path):
    first, id = await created(tmp_path)
    second = service(tmp_path);old = second.read(id)
    first.mutate(id, edit_request(first.read(id), 'Newer committed', completion='slot'))
    result = second.mutate(id, edit_request(old, 'Stale store', completion='slot'))
    assert result.persistence == 'failed' and second.save_errors[id] == 'PROJECT_REVISION_CHANGED'
    assert service(tmp_path).read(id).project.document.profile.text.text == 'Newer committed'


@pytest.mark.asyncio
async def test_corrupt_project_is_isolated_and_tombstones_never_resurrect_or_allow_save(tmp_path):
    store, id = await created(tmp_path)
    second = await store.select((ROOT / 'E1.txt').read_bytes(), 'second.txt', True)
    other = second.project_id
    await finish(store, other, store.start(other))
    path = tmp_path / 'FoldCV/projects' / id / 'workspace.json';path.write_text('{broken')
    reopened = service(tmp_path)
    assert reopened.read(other).project.document.candidate.name.text == 'Ирина Примерова'
    with pytest.raises(ProjectFailure, match='PROJECT_LOAD_FAILED'):reopened.read(id)
    retained = reopened.read(other)
    registry = reopened.storage.registry()
    next(entry for entry in registry.entries if entry.project_id == other).tombstoned = True
    atomic_write(tmp_path / 'FoldCV/registry.json', storage_module.encoded(registry.model_dump(mode='json', by_alias=True)))
    with pytest.raises(ProjectStoreFailure, match='PROJECT_DELETED'):reopened.storage.save(retained, reopened.originals, reopened.artifacts)
    with pytest.raises(ProjectFailure, match='PROJECT_DELETED'):reopened.read(other)
    with pytest.raises(ProjectFailure, match='PROJECT_DELETED'):service(tmp_path).read(other)


@pytest.mark.asyncio
@pytest.mark.parametrize('target', ['workspace', 'source', 'identity'])
async def test_symlink_or_hardlink_project_files_fail_closed_without_touching_external_files(target, tmp_path):
    store, id = await created(tmp_path)
    directory = tmp_path / 'FoldCV/projects' / id
    selected = directory / 'workspace.json' if target == 'workspace' else directory / '.project-identity.json' if target == 'identity' else next((directory / 'sources').iterdir())
    external = tmp_path / 'external';external.write_bytes(selected.read_bytes());external.chmod(0o600)
    before = external.read_bytes();selected.unlink()
    if target == 'source':os.link(external, selected)
    else:selected.symlink_to(external)
    with pytest.raises(ProjectFailure):service(tmp_path).read(id)
    assert external.read_bytes() == before and external.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_snapshot_committed_before_registry_failure_recovers_without_inference(tmp_path, monkeypatch):
    store, id = await created(tmp_path)
    write = storage_module.atomic_write
    fail = True
    def failing(path, data):
        if fail and path.name == 'registry.json':raise OSError('synthetic registry failure')
        write(path, data)
    monkeypatch.setattr(storage_module, 'atomic_write', failing)
    result = store.mutate(id, edit_request(store.read(id), 'Recover committed snapshot', completion='slot'))
    assert result.persistence == 'failed'
    fail = False
    provider = CreationProvider();reopened = service(tmp_path, provider)
    assert reopened.read(id).project.document.profile.text.text == 'Recover committed snapshot'
    assert provider.calls == [] and reopened.durability(id) == 'durable'
    assert reopened.storage.registry().entries[0].title == reopened.read(id).title


@pytest.mark.asyncio
async def test_missing_optional_render_cache_preserves_document_and_does_not_start_a_model(tmp_path):
    store, id = await created(tmp_path)
    before = store.read(id)
    next((tmp_path / 'FoldCV/projects' / id / 'renders').iterdir()).unlink()
    provider = CreationProvider();reopened = service(tmp_path, provider);workspace = reopened.read(id)
    assert workspace.project.document == before.project.document and provider.calls == []
    assert not workspace.project.renders[0].artifact_available and reopened.artifacts == {}


@pytest.mark.asyncio
async def test_storage_failure_and_reads_keep_candidate_text_out_of_console_and_errors(tmp_path, monkeypatch, capsys):
    store = service(tmp_path)
    selected = await store.select(b'PRIVATE_STORAGE_EVIDENCE', 'private.txt', True)
    write = storage_module.atomic_write
    def failing(path, data):
        if path.name == 'workspace.json':raise OSError('synthetic error')
        write(path, data)
    monkeypatch.setattr(storage_module, 'atomic_write', failing)
    assert store.persist(selected.project_id) == 'failed'
    assert store.save_errors[selected.project_id] == 'PROJECT_SAVE_FAILED'
    output = capsys.readouterr()
    assert 'PRIVATE_STORAGE_EVIDENCE' not in output.out + output.err
