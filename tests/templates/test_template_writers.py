"""Template authoring uses the existing real writer and canonical commit boundary."""

import httpx
import pytest
import threading
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from packages.resume_core.background_clock import ControlledDeadlines
from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_writers import WriterSessions
from packages.resume_core.models.background import WriterOpenV1, WriterProofV1, WriterViewV1
from packages.resume_core.models.template_writer import WriterAdvanceV2, WriterCheckpointV2, WriterMutationV2, WriterViewV2
from packages.resume_core.template_dependencies import selector
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.rich_dependencies import dependency
from tests.templates.test_materialize import fallback_edit, issue_workspace
from tests.templates.test_template_publication import TemplatePublicationFixture


class TemplateWriterFixture(TemplatePublicationFixture):
    def __init__(self, root, workspace=None, sources=None):
        super().__init__(root, create=False)
        if workspace is None:
            workspace, sources = issue_workspace()
        self.project = workspace.project_id
        self.originals = {(self.project, key): raw for key, raw in sources.items()}
        self.canonical.save(workspace, self.originals, {})
        self.jobs.open(self.project)
        self.elapsed = ControlledDeadlines()
        self.publisher.authority.clock = self.elapsed
        self.writers = WriterSessions(self.publisher)
        request = WriterOpenV1(schemaVersion=1, sessionId='editor-session', incarnation='connection-one',
            credential='synthetic_writer_credential_0123456789', canonicalRevision=workspace.project_revision,
            canonicalSha256=digest_bytes(workspace), actionCursor=0)
        self.view = self.writers.open(self.project, request)
        self.proof = WriterProofV1(schemaVersion=1, lineage=self.view.writer.lineage, epoch=self.view.writer.epoch,
            sessionId=self.view.writer.session_id, incarnation=self.view.writer.incarnation, credential=request.credential)

    def advance_request(self, cursor=0, touches=()):
        current = self.current()
        return WriterAdvanceV2(schemaVersion=2, proof=self.proof, canonicalRevision=current.project_revision,
            canonicalSha256=digest_bytes(current), actionCursor=cursor, touches=list(touches))

    def edit(self):
        command = fallback_edit(self.current())
        command.capture.session_id = self.proof.session_id
        return command

    def save_request(self):
        command = self.edit()
        return WriterMutationV2(**self.advance_request(1, [{'cursor': 1, 'mutation': command}]).model_dump(by_alias=True),
            mutation=command)


def test_writer_v2_saves_one_fact_document_issue_transaction_and_replays_exact_bytes(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    assert fixture.view.schema_version == 2 and fixture.view.workspace.schema_version == 7
    with pytest.raises(ValueError):
        WriterViewV1.model_validate(fixture.view.model_dump(by_alias=True))
    request = fixture.save_request()
    saved = fixture.writers.save(fixture.project, request, originals=fixture.originals)
    assert saved.schema_version == 2 and saved.canonical_ready and not saved.replayed
    assert saved.response.snapshot == saved.response.presentation.snapshot
    assert [issue.state for issue in saved.workspace.project.import_issues] == ['retired', 'active']
    assert saved.writer.acknowledged_cursor == 1 and saved.workspace == fixture.current()
    repeated = fixture.writers.save(fixture.project, request, originals=fixture.originals)
    assert repeated.replayed and repeated.workspace == saved.workspace
    assert repeated.mutation_wire == request.mutation.model_dump_json(by_alias=True)
    assert len(saved.workspace.mutation_replay) == 1
    assert not fixture.jobs.load(fixture.project).jobs and not fixture.jobs.load(fixture.project).inverses
    assert dependency(saved.workspace, 'field', selector('issue', saved.workspace.project.import_issues[0].id)).fingerprint


def test_unknown_preparation_reference_cannot_silently_use_the_raw_save_path(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    before = canonical(fixture.current())
    value = fixture.save_request().model_dump(by_alias=True)
    value['preparation'] = {'requestHash': 'a' * 64}
    with pytest.raises(BackgroundFailure, match='REQUEST_EXPIRED'):
        fixture.writers.save(fixture.project, WriterMutationV2.model_validate(value), originals=fixture.originals)
    assert canonical(fixture.current()) == before


@pytest.mark.parametrize('change', ['wire', 'snapshot', 'presentation', 'mutation'])
def test_writer_v2_rejects_unbound_response_wire_or_acknowledgment(tmp_path, change):
    fixture = TemplateWriterFixture(tmp_path)
    saved = fixture.writers.save(fixture.project, fixture.save_request(), originals=fixture.originals)
    value = saved.model_dump(mode='json', by_alias=True)
    if change == 'wire':
        value['workspaceWire'] += ' '
    elif change == 'snapshot':
        value['response']['snapshot']['packageHash'] = '0' * 64
    elif change == 'presentation':
        value['response']['presentation']['recipe']['style']['page']['first_body_top'] += 1
    else:
        value['mutationWire'] = value['mutationWire'].replace('Exact human correction', 'Forged acknowledgment')
    with pytest.raises(ValueError):
        WriterViewV2.model_validate(value)


def test_writer_v2_private_checkpoint_roundtrips_template_facts_and_presentation(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    current = fixture.current()
    payload = {'schemaVersion': 2, 'document': current.project.document.model_dump(by_alias=True),
        'facts': current.project.facts.model_dump(by_alias=True), 'outbox': [], 'assetPins': [],
        'touches': [{'cursor': 1, 'mutation': fixture.edit().model_dump(by_alias=True)}],
        'importIssues': [issue.model_dump(by_alias=True) for issue in current.project.import_issues],
        'importCoverage': [value.model_dump(by_alias=True) for value in current.project.import_coverage]}
    record = fixture.writers.checkpoint(fixture.project, WriterCheckpointV2(schemaVersion=2, proof=fixture.proof,
        id='local-checkpoint', sequence=1, actionCursor=1, baseRevision=current.project_revision,
        baseSha256=digest_bytes(current), payload=payload))
    from packages.resume_core.models.background import WriterDraftReferenceV1
    read = fixture.writers.read_draft(fixture.project, WriterDraftReferenceV1(schemaVersion=1,
        proof=fixture.proof, id=record.id))
    assert read.schema_version == 2 and read.payload.schema_version == 2
    assert read.payload.document == current.project.document and read.payload.facts == current.project.facts
    assert read.payload.import_issues == current.project.import_issues and read.payload.touches[0].mutation == fixture.edit()


@pytest.mark.parametrize('coherent', [False, True])
def test_v2_private_draft_use_requires_document_facts_and_issue_state_together(tmp_path, coherent):
    from packages.resume_core.models.template_writer import WriterDraftResolveV2
    from packages.resume_core.rich_mutations import apply_rich_mutation
    fixture = TemplateWriterFixture(tmp_path)
    before = fixture.current()
    mutation = fixture.edit()
    pending, _replayed = apply_rich_mutation(before, mutation)
    issues = pending.project.import_issues if coherent else before.project.import_issues
    record = fixture.writers.checkpoint(fixture.project, WriterCheckpointV2(schemaVersion=2, proof=fixture.proof,
        id='pending-edit', sequence=1, actionCursor=1, baseRevision=before.project_revision,
        baseSha256=digest_bytes(before), payload={'schemaVersion': 2,
            'document': pending.project.document.model_dump(by_alias=True), 'facts': pending.project.facts.model_dump(by_alias=True),
            'outbox': [mutation.model_dump(by_alias=True)], 'assetPins': [],
            'touches': [{'cursor': 1, 'mutation': mutation.model_dump(by_alias=True)}],
            'importIssues': [issue.model_dump(by_alias=True) for issue in issues],
            'importCoverage': [value.model_dump(by_alias=True) for value in pending.project.import_coverage]}))
    command = WriterDraftResolveV2(schemaVersion=2, proof=fixture.proof, id=record.id,
        sequence=record.sequence, payloadSha256=record.payload_sha256, canonicalRevision=before.project_revision,
        canonicalSha256=digest_bytes(before), mutation=mutation)
    if not coherent:
        with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
            fixture.writers.use_draft(fixture.project, command, originals=fixture.originals)
        assert fixture.current() == before
        return
    restored = fixture.writers.use_draft(fixture.project, command, originals=fixture.originals)
    assert restored.schema_version == 2 and restored.workspace.project.import_issues[0].state == 'retired'
    assert restored.workspace.project.document == pending.project.document
    assert not fixture.jobs.load(fixture.project).drafts


@pytest.mark.asyncio
async def test_existing_writer_routes_dispatch_v2_without_accepting_a_v1_content_command(tmp_path):
    from types import SimpleNamespace
    from resume_api.jobs.writers import mount_writers
    fixture = TemplateWriterFixture(tmp_path)
    adopted = []
    projects = SimpleNamespace(originals=fixture.originals, artifacts={}, images={}, state_lock=threading.RLock())
    service = SimpleNamespace(enabled=True, writers=fixture.writers, projects=projects,
        publication=SimpleNamespace(adopt=lambda *args: adopted.append(args)))
    app = FastAPI()
    @app.exception_handler(BackgroundFailure)
    async def failure(_request, error):
        return JSONResponse({'error': {'code': error.code}}, status_code=409)
    mount_writers(app, service)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://foldcv.test') as client:
        path = '/v1/rich/projects/' + fixture.project + '/writer'
        saved = await client.post(path + '/save', json=fixture.save_request().model_dump(mode='json', by_alias=True))
        assert saved.status_code == 200 and saved.json()['schemaVersion'] == 2 and len(adopted) == 1
        assert saved.content == canonical(WriterViewV2.model_validate(saved.json()))
        from tests.templates.test_template_local_history import history_request
        ack = WriterViewV2.model_validate(saved.json()).local_history_ack
        undo = await client.post(path + '/history/local', json=history_request(fixture, ack).model_dump(mode='json', by_alias=True))
        assert undo.status_code == 200 and undo.json()['schemaVersion'] == 2 and len(adopted) == 2
        restored = WriterViewV2.model_validate(undo.json())
        assert restored.workspace.project.import_issues[0].state == 'active'
        request = fixture.advance_request(1).model_dump(mode='json', by_alias=True)
        request['schemaVersion'] = 1
        rejected = await client.post(path + '/flush', json=request)
        assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'JOB_SCOPE_INVALID'
