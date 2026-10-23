"""V7 pending input survives in the existing private draft; Python checks shape and bounds only."""

import json

import pytest
from pydantic import ValidationError

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.background import WriterDraftCommandV1, WriterDraftReferenceV1
from packages.resume_core.models.template_writer import DraftPayloadV2, TemplateQueueDraftV1, WriterCheckpointV2
from tests.templates.test_template_preparation_contracts import preparation
from tests.templates.test_template_writers import TemplateWriterFixture

CONTAINER = {'blockId': 'block-a', 'kind': 'content', 'cellId': None}
STYLES = {'bold': False, 'italic': False, 'underline': False, 'strike': False, 'code': False,
    'textColor': 'default', 'backgroundColor': 'default'}
PREPARED = json.dumps(preparation({'kind': 'replace_text', 'range': {'blockId': 'block-a', 'beforeRevision': 1, 'cellId': None,
    'field': 'content', 'start': 3, 'end': 3, 'insertionTarget': {'kind': 'literal'}}, 'text': '!', 'styles': {}}))


def intent(local, mutation, **operation):
    value = {'kind': 'replace_text', 'container': CONTAINER, 'start': 3, 'end': 3, 'text': '!', 'styles': STYLES, 'side': 'before'}
    return {'localId': local, 'actionId': 'session:1', 'actionToken': 0, 'clientMutationId': mutation,
        'operation': {**value, **operation}, 'prior': [{'container': CONTAINER, 'text': 'By Shared'}]}


def queue(**changes):
    value = {'schemaVersion': 1, 'intents': [intent('intent-1', 'edit'), intent('intent-2', 'edit-2', start=4, end=4)],
        'head': {'clientMutationId': 'edit', 'preparationWire': PREPARED, 'stage': 'prepared'},
        'locals': [{'local': 'local-1', 'canonical': 'block-b'}],
        'editorTexts': [{'container': CONTAINER, 'text': 'By !!Shared'}]}
    return {**value, **changes}


def payload(fixture, template_queue):
    current = fixture.current()
    value = {'schemaVersion': 2, 'document': current.project.document.model_dump(by_alias=True),
        'facts': current.project.facts.model_dump(by_alias=True), 'outbox': [], 'assetPins': [],
        'touches': [{'cursor': 1, 'mutation': None}],
        'importIssues': [issue.model_dump(by_alias=True) for issue in current.project.import_issues],
        'importCoverage': [item.model_dump(by_alias=True) for item in current.project.import_coverage]}
    return value if template_queue is None else {**value, 'templateQueue': template_queue}


def checkpoint(fixture, template_queue):
    current = fixture.current()
    return fixture.writers.checkpoint(fixture.project, WriterCheckpointV2(schemaVersion=2, proof=fixture.proof,
        id='v7-draft', sequence=1, actionCursor=1, baseRevision=current.project_revision,
        baseSha256=digest_bytes(current), payload=payload(fixture, template_queue)))


def command(fixture, record):
    current = fixture.current()
    return WriterDraftCommandV1(schemaVersion=1, proof=fixture.proof, id=record.id, sequence=record.sequence,
        payloadSha256=record.payload_sha256, canonicalRevision=current.project_revision, canonicalSha256=digest_bytes(current))


def test_queue_record_roundtrips_and_an_absent_record_keeps_existing_v2_bytes(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    record = checkpoint(fixture, queue())
    read = fixture.writers.read_draft(fixture.project, WriterDraftReferenceV1(schemaVersion=1, proof=fixture.proof, id=record.id))
    assert read.payload.template_queue == TemplateQueueDraftV1.model_validate(queue())
    assert read.payload.template_queue.head.preparation_wire == PREPARED
    plain = DraftPayloadV2.model_validate(payload(fixture, None))
    assert 'templateQueue' not in plain.model_dump(mode='json', by_alias=True)


@pytest.mark.parametrize('change', [
    {'head': {'clientMutationId': 'edit-2', 'preparationWire': PREPARED, 'stage': 'frozen'}},
    {'head': {'clientMutationId': 'edit', 'preparationWire': '{"schemaVersion":1}', 'stage': 'frozen'}},
    {'intents': [intent('same', 'edit'), intent('same', 'edit-2')]},
    {'intents': [intent(f'intent-{index}', f'edit-{index}') for index in range(101)], 'head': None},
    {'editorTexts': [{'container': CONTAINER, 'text': 'a'}, {'container': CONTAINER, 'text': 'b'}]},
], ids=['head-not-first', 'head-wire', 'duplicate-intent', 'over-capacity', 'duplicate-text'])
def test_incoherent_or_unbounded_queue_records_are_rejected(change):
    with pytest.raises(ValidationError):
        TemplateQueueDraftV1.model_validate(queue(**change))


@pytest.mark.parametrize('operation', [{'side': None}, {'start': 5, 'end': 4}, {'container': {**CONTAINER, 'cellId': 'cell'}}],
    ids=['collapsed-without-side', 'reversed', 'content-with-cell'])
def test_local_operations_are_shape_checked(operation):
    with pytest.raises(ValidationError):
        TemplateQueueDraftV1.model_validate(queue(intents=[intent('intent-1', 'edit', **operation)]))


def test_pending_input_reattaches_the_writer_and_ends_only_the_server_draft(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    record = checkpoint(fixture, queue())
    assert fixture.jobs.load(fixture.project).writer.status == 'recovering'
    view = fixture.writers.pending_input_draft(fixture.project, command(fixture, record))
    assert view.writer.status == 'attached' and view.writer.acknowledged_cursor == 1
    assert not fixture.jobs.load(fixture.project).drafts


def test_pending_input_requires_a_queue_record(tmp_path):
    fixture = TemplateWriterFixture(tmp_path)
    record = checkpoint(fixture, None)
    with pytest.raises(BackgroundFailure, match='JOB_SCOPE_INVALID'):
        fixture.writers.pending_input_draft(fixture.project, command(fixture, record))
    assert fixture.jobs.load(fixture.project).drafts
