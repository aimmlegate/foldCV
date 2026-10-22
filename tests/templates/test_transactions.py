"""One guarded candidate owns authored text, human cells, issues and inverses."""

from dataclasses import replace

import pytest

from packages.resume_core.models.template_import import ImportIssue
from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation, mutation_sha256
from packages.resume_core.template_facts import ambiguous_edit, effective_extension_values, human_edit
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_mutations import HistoryAuthorization
from packages.resume_core.templates.compiler import sha256
from tests.templates.storage_fixtures import workspace


def request(value, steps, identifier='human-edit'):
    return TemplateMutationV1(schemaVersion=1, projectId=value.project_id, clientMutationId=identifier,
        actionId=identifier, kind='typing', capture={'sessionId': 'session', 'actionId': identifier,
            'actionToken': 1, 'dependencies': []}, steps=steps, history={'kind': 'edit', 'originActionId': None})


def extension_step(value, record):
    current = next(r for r in value.project.facts.extensions if r.id == record.id)
    return {'kind': 'put_extension', 'beforeRevision': current.revision, 'record': record.model_dump(by_alias=True)}


def authorization(value, inverse):
    return HistoryAuthorization(value.project_id, value.document_revision, inverse.capture.session_id,
        inverse.capture.action_token, inverse.history.origin_action_id, mutation_sha256(inverse))


def issue(identifier, target):
    return ImportIssue(id=identifier, ruleId='support', taskId='synthetic-task', targetIds=[target],
        blockIds=['block-' + target], category='content_violation', code='UNSUPPORTED_WORDING', message='Check source',
        importedFingerprint=sha256(identifier.encode()), reviewInputHash=None, lifecycleId='life-' + identifier,
        state='active', retiredByAction=None)


def test_one_transaction_and_scoped_undo_redo_keep_unrelated_later_edits(monkeypatch):
    before, _ = workspace()
    before.project.import_issues = [issue('issue-a', 'paper-a'), issue('issue-b', 'paper-b')]
    edited_facts = human_edit(before.project.facts, 'paper-a', 'title', 'Exact human wording')
    block = before.project.document.regions[2].blocks[0]
    steps = [extension_step(before, edited_facts.extensions[0]),
        {'kind': 'replace_inline_range', 'blockId': block.id, 'beforeRevision': block.revision,
            'cellId': None, 'field': 'content', 'start': 0, 'end': len(block.content[0].text),
            'content': [{**block.content[0].model_dump(by_alias=True), 'text': 'Exact human wording'}]},
        {'kind': 'set_issue_state', 'issueId': 'issue-a', 'beforeLifecycleId': 'life-issue-a', 'beforeState': 'active',
            'afterLifecycleId': 'retired-issue-a', 'afterState': 'retired', 'actionId': 'human-edit',
            'importedFingerprint': before.project.import_issues[0].imported_fingerprint}]
    def forbidden(*_args, **_kwargs):
        raise AssertionError('human transaction must not run dynamic template assertions')
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload', forbidden)
    changed, _ = apply_rich_mutation(before, request(before, steps))
    assert changed.project.facts.extensions[0].cells[0].state == 'human_raw'
    assert changed.project.facts.extensions[0].cells[0].typed_value is None
    assert changed.project.import_issues[0].state == 'retired'
    assert changed.project.import_issues[1] == before.project.import_issues[1]
    inverse = inverse_template_mutation(before, changed, origin_action_id='human-edit',
        mutation_id='undo', session_id='session', action_token=2)
    later_facts = human_edit(changed.project.facts, 'paper-b', 'year', 'forthcoming')
    later, _ = apply_rich_mutation(changed, request(changed, [extension_step(changed, later_facts.extensions[1])], 'later'))
    with pytest.raises(RichMutationFailure, match='STALE_MUTATION'):
        apply_rich_mutation(later, inverse)
    restored, _ = apply_rich_mutation(later, inverse, history_authorization=authorization(later, inverse))
    assert restored.project.facts.extensions[0].cells[0].typed_value == 'Shared title'
    assert restored.project.document.regions[2].blocks[0].content[0].text == 'Shared title'
    assert restored.project.facts.extensions[1] == later.project.facts.extensions[1]
    assert restored.project.import_issues[0].state == 'active'
    redo = inverse_template_mutation(later, restored, origin_action_id='human-edit',
        mutation_id='redo', session_id='session', action_token=3, kind='redo')
    replayed, _ = apply_rich_mutation(restored, redo, history_authorization=authorization(restored, redo))
    assert replayed.project.facts.extensions[0].cells[0].raw_input == 'Exact human wording'
    assert replayed.project.facts.extensions[1] == later.project.facts.extensions[1]
    assert replayed.project.import_issues[0].state == 'retired'
    assert replayed.project.import_issues[1] == before.project.import_issues[1]


def test_rejected_combined_candidate_leaves_original_bytes_and_facts_exact():
    before, _ = workspace()
    original = before.model_dump_json(by_alias=True)
    edited = human_edit(before.project.facts, 'paper-a', 'year', 'forthcoming')
    invalid = before.project.document.regions[2].blocks[0].model_copy(deep=True)
    invalid.content[0].record_id = 'missing-record'
    steps = [extension_step(before, edited.extensions[0]), {'kind': 'put_block', 'parentId': 'main',
        'afterId': None, 'beforeRevision': invalid.revision, 'block': invalid.model_dump(by_alias=True)}]
    with pytest.raises(RichMutationFailure, match='RICH_PATCH_INVALID'):
        apply_rich_mutation(before, request(before, steps))
    assert before.model_dump_json(by_alias=True) == original


@pytest.mark.parametrize('corruption', ['evidence', 'typed_assertion', 'duplicate_target', 'cell_id'])
def test_manual_mutation_rejects_identity_or_assertion_forgery(corruption):
    before, _ = workspace()
    record = before.project.facts.extensions[0].model_copy(deep=True)
    if corruption == 'evidence':
        record.cells[0].evidence[0].slice_hash = sha256(b'forged')
    elif corruption == 'typed_assertion':
        record.cells[0].typed_value = record.cells[0].raw_input = 'Unsupported model assertion'
    elif corruption == 'cell_id':
        record.cells[0].id = 'new-cell'
    steps = [extension_step(before, record)]
    if corruption == 'duplicate_target':
        steps *= 2
    with pytest.raises(RichMutationFailure):
        apply_rich_mutation(before, request(before, steps))


def test_history_authorization_cannot_survive_another_document_revision_or_token():
    before, _ = workspace()
    edited = human_edit(before.project.facts, 'paper-a', 'year', 'forthcoming')
    changed, _ = apply_rich_mutation(before, request(before, [extension_step(before, edited.extensions[0])]))
    inverse = inverse_template_mutation(before, changed, origin_action_id='human-edit',
        mutation_id='undo', session_id='session', action_token=2)
    proof = authorization(changed, inverse)
    for wrong in [replace(proof, document_revision=1), replace(proof, action_token=1), replace(proof, request_sha256=sha256(b'old'))]:
        with pytest.raises(RichMutationFailure, match='STALE_MUTATION'):
            apply_rich_mutation(changed, inverse, history_authorization=wrong)


def test_issue_retirement_requires_its_actual_manual_scope():
    before, _ = workspace()
    warning = issue('field-warning', 'paper-a')
    warning.target_ids = ['a-title']
    before.project.import_issues = [warning]
    retire = {'kind': 'set_issue_state', 'issueId': warning.id, 'beforeLifecycleId': warning.lifecycle_id,
        'beforeState': 'active', 'afterLifecycleId': 'retired', 'afterState': 'retired',
        'actionId': 'human-edit', 'importedFingerprint': warning.imported_fingerprint}
    with pytest.raises(RichMutationFailure):
        apply_rich_mutation(before, request(before, [retire]))
    year = human_edit(before.project.facts, 'paper-a', 'year', 'forthcoming')
    with pytest.raises(RichMutationFailure):
        apply_rich_mutation(before, request(before, [extension_step(before, year.extensions[0]), retire]))
    title = human_edit(before.project.facts, 'paper-a', 'title', 'Human title')
    changed, _ = apply_rich_mutation(before, request(before, [extension_step(before, title.extensions[0]), retire]))
    assert changed.project.import_issues[0].state == 'retired'


def test_explicit_model_context_keeps_authoritative_raw_and_pending_scope_values():
    original, _ = workspace()
    facts = human_edit(original.project.facts, 'paper-a', 'year', '  forthcoming  ')
    facts = ambiguous_edit(facts, ['a-title', 'a-journal'], 'Human wording across both fields',
        'manual-scope-action', ['block-paper-a'], scope_id='pending-scope')
    values = effective_extension_values(facts, ['paper-a'])
    year = next(value for value in values if value.cell.field_key == 'year')
    assert year.cell.raw_input == '  forthcoming  ' and year.cell.typed_value is None
    pending = [value for value in values if value.cell.state == 'pending_manual']
    assert len(pending) == 2 and all(value.manual_scope.raw_input == 'Human wording across both fields' for value in pending)
    assert all(value.cell.typed_value is None for value in pending)
    facts.extensions[0].cells[3].state = 'uncertain'
    facts.extensions[0].cells[3].typed_value = None
    assert 'url' not in {value.cell.field_key for value in effective_extension_values(facts, ['paper-a'])}


def test_extension_only_inverse_obeys_the_existing_history_capacity(monkeypatch):
    from packages.resume_core import template_inverse as module
    from packages.resume_core.background_store import BackgroundFailure
    before, _ = workspace()
    edited = human_edit(before.project.facts, 'paper-a', 'year', 'forthcoming')
    changed, _ = apply_rich_mutation(before, request(before, [extension_step(before, edited.extensions[0])]))
    monkeypatch.setattr(module, 'LIMITS', replace(module.LIMITS, inverse_bytes=1024))
    with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
        inverse_template_mutation(before, changed, origin_action_id='human-edit',
            mutation_id='undo', session_id='session', action_token=2)


def test_new_human_cell_keeps_existing_cell_ids_and_bypasses_template_assertions():
    before, _ = workspace()
    supplied = before.project.facts.extensions[0].cells.pop(1)
    original_ids = [cell.id for cell in before.project.facts.extensions[0].cells]
    record = before.project.facts.extensions[0].model_copy(deep=True)
    supplied.raw_input, supplied.typed_value = 'New human journal', None
    supplied.state, supplied.origin, supplied.user_corrected = 'human_raw', 'human', True
    supplied.evidence = []
    record.cells.append(supplied)
    changed, _ = apply_rich_mutation(before, request(before, [extension_step(before, record)]))
    assert [cell.id for cell in changed.project.facts.extensions[0].cells[:-1]] == original_ids
    assert changed.project.facts.extensions[0].cells[-1].raw_input == 'New human journal'
    inverse = inverse_template_mutation(before, changed, origin_action_id='human-edit',
        mutation_id='undo-new-cell', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(changed, inverse, history_authorization=authorization(changed, inverse))
    assert [cell.id for cell in restored.project.facts.extensions[0].cells] == original_ids
    redo = inverse_template_mutation(changed, restored, origin_action_id='human-edit',
        mutation_id='redo-new-cell', session_id='session', action_token=3, kind='redo')
    replayed, _ = apply_rich_mutation(restored, redo, history_authorization=authorization(restored, redo))
    assert [cell.id for cell in replayed.project.facts.extensions[0].cells] == [*original_ids, supplied.id]
    assert replayed.project.facts.extensions[0].cells[-1].raw_input == 'New human journal'
