"""Shared human scopes survive atomic issue history, deletion and portable storage."""

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from packages.resume_core.models.template_document import TemplateParagraphBlock
from packages.resume_core.models.rich_facts import WorkingPeriod
from packages.resume_core.models.template_facts import WorkingFactsV2
from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.rich_fields import field_key, working_field
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.templates.compiler import canonical
from tests.templates.test_relation_transactions import related_workspace
from tests.templates.test_transactions import authorization, extension_step, issue, request


RAW = 'Exact human company — exact human role'


def scoped_workspace():
    value, originals = related_workspace()
    presentation = value.project.document.regions[2].blocks[0].presentation
    company = next(record for record in value.project.facts.records if record.id == 'employer-a')
    parts = []
    for name in ['employer', 'role']:
        if parts:
            parts.append({'type': 'text', 'text': ' — ', 'styles': {}})
        parts.append({'type': 'fact_field', 'bindingId': name + '-fragment', 'bindingRootId': name + '-root',
            'recordId': company.id, 'fieldKey': name, 'cellId': field_key(company.id, name),
            'occurrenceId': name + '-root', 'complete': True, 'presentation': presentation,
            'text': working_field(company, name).raw_text, 'styles': {}, 'syncedFactRevision': 1})
    value.project.document.regions[2].blocks.insert(0, TemplateParagraphBlock(type='paragraph', id='job-label',
        revision=1, props={}, content=parts, children=[], provenance=[], presentation=presentation))
    value.project.import_issues = [issue('issue-a', field_key(company.id, 'employer')),
        issue('issue-b', field_key('employer-b', 'role'))]
    for finding in value.project.import_issues:
        finding.block_ids = ['job-label']
    return WorkspaceV7.model_validate(value.model_dump(by_alias=True)), originals


def pending_steps(value, *, identifier='joined-edit', text=RAW, names=('employer', 'role')):
    previous = next(record for record in value.project.facts.records if record.id == 'employer-a')
    changed = previous.model_copy(deep=True)
    for name in names:
        field = working_field(changed, name)
        field.value, field.status, field.pending_raw_text, field.user_corrected = None, 'pending', text, True
    cells = [field_key(changed.id, name) for name in names]
    scope = {'id': 'scope-' + identifier, 'actionId': identifier, 'rawInput': text, 'cellIds': cells, 'blockIds': ['job-label']}
    steps = [{'kind': 'put_record', 'beforeRevision': previous.revision, 'record': changed.model_dump(by_alias=True)},
        {'kind': 'put_manual_scope', 'scope': scope}]
    steps.extend({'kind': 'set_builtin_manual_scope', 'cellId': cell,
        'beforeScopeId': value.project.facts.builtin_manual_scopes.get(cell), 'afterScopeId': scope['id']} for cell in cells)
    return steps, scope


def joined_edit(before):
    steps, scope = pending_steps(before)
    block = before.project.document.regions[2].blocks[0]
    steps += [{'kind': 'replace_inline_range', 'blockId': block.id, 'beforeRevision': block.revision,
        'cellId': None, 'field': 'content', 'start': 0, 'end': sum(len(part.text) for part in block.content),
        'content': [{'type': 'text', 'text': RAW, 'styles': {}}]},
        {'kind': 'set_issue_state', 'issueId': 'issue-a', 'beforeLifecycleId': 'life-issue-a', 'beforeState': 'active',
            'afterLifecycleId': 'retired-issue-a', 'afterState': 'retired', 'actionId': 'joined-edit',
            'importedFingerprint': before.project.import_issues[0].imported_fingerprint}]
    return request(before, steps, 'joined-edit'), scope


def test_old_facts_canonical_bytes_remain_exact_with_no_scope_map():
    raw = Path('tests/fixtures/synthetic/templates/working-facts-v2-before-scopes.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '62e95339f39abf31449fd7e22ab820d3e82aac509ca7f20b5bf48d3e174a9578'
    assert canonical(WorkingFactsV2.model_validate_json(raw)) == raw


def test_joined_human_scope_and_issue_undo_redo_are_one_atomic_history_action(monkeypatch):
    before, _sources = scoped_workspace()
    command, scope = joined_edit(before)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('human edits must not invoke template assertions')
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload', forbidden)
    changed, _ = apply_rich_mutation(before, command)
    current = next(record for record in changed.project.facts.records if record.id == 'employer-a')
    assert current.employer.value is None and current.role.value is None
    assert current.employer.pending_raw_text == current.role.pending_raw_text == RAW
    assert changed.project.facts.builtin_manual_scopes == {cell: scope['id'] for cell in scope['cellIds']}
    assert changed.project.import_issues[0].state == 'retired'
    assert changed.project.import_issues[1] == before.project.import_issues[1]
    inverse = inverse_template_mutation(before, changed, origin_action_id='joined-edit',
        mutation_id='undo', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(changed, inverse, history_authorization=authorization(changed, inverse))
    assert not restored.project.facts.builtin_manual_scopes
    assert restored.project.import_issues[0].state == 'active'
    assert next(record for record in restored.project.facts.records if record.id == current.id).employer.value == 'employer-a'
    assert restored.project.facts.manual_scopes[0].raw_input == RAW
    redo = inverse_template_mutation(changed, restored, origin_action_id='joined-edit',
        mutation_id='redo', session_id='session', action_token=3, kind='redo')
    replayed, _ = apply_rich_mutation(restored, redo, history_authorization=authorization(restored, redo))
    assert replayed.project.facts.builtin_manual_scopes == changed.project.facts.builtin_manual_scopes
    assert replayed.project.import_issues[0].state == 'retired' and replayed.project.import_issues[1].state == 'active'
    assert replayed.project.document.regions[2].blocks[0].content[0].text == RAW


@pytest.mark.parametrize('failure', ['typed_value', 'wrong_raw', 'missing_cell', 'missing_reference', 'extension_guard', 'stale_reference', 'duplicate_reference', 'unknown_cell'])
def test_invalid_scope_candidate_is_rejected_without_partial_changes(failure):
    before, _sources = scoped_workspace()
    command, _scope = joined_edit(before)
    value = command.model_dump(by_alias=True)
    if failure == 'typed_value':
        value['steps'][0]['record']['employer']['value'] = 'obsolete assertion'
    elif failure == 'wrong_raw':
        value['steps'][1]['scope']['rawInput'] = 'different human text'
    elif failure == 'missing_cell':
        value['steps'][1]['scope']['cellIds'].pop()
    elif failure == 'missing_reference':
        value['steps'].pop(2)
    elif failure == 'extension_guard':
        value['steps'][1]['scope']['cellIds'].append('missing-extension-cell')
    elif failure == 'stale_reference':
        value['steps'][2]['beforeScopeId'] = 'stale-scope'
    elif failure == 'duplicate_reference':
        value['steps'].append(deepcopy(value['steps'][2]))
    else:
        value['steps'] = [{'kind': 'set_builtin_manual_scope', 'cellId': 'missing-canonical-cell',
            'beforeScopeId': None, 'afterScopeId': None}]
    original = canonical(before)
    with pytest.raises(RichMutationFailure):
        apply_rich_mutation(before, TemplateMutationV1.model_validate(value))
    assert canonical(before) == original


def test_scope_clear_requires_resolved_field_and_clears_only_that_current_reference():
    before, _sources = scoped_workspace()
    command, scope = joined_edit(before)
    changed, _ = apply_rich_mutation(before, command)
    cell = scope['cellIds'][0]
    clear = {'kind': 'set_builtin_manual_scope', 'cellId': cell, 'beforeScopeId': scope['id'], 'afterScopeId': None}
    with pytest.raises(RichMutationFailure):
        apply_rich_mutation(changed, request(changed, [clear], 'invalid-clear'))
    current = next(record for record in changed.project.facts.records if record.id == 'employer-a')
    resolved = current.model_copy(deep=True)
    resolved.employer.value, resolved.employer.raw_text = 'Exact human company', 'Exact human company'
    resolved.employer.status, resolved.employer.pending_raw_text = 'known', None
    saved, _ = apply_rich_mutation(changed, request(changed, [
        {'kind': 'put_record', 'beforeRevision': current.revision, 'record': resolved.model_dump(by_alias=True)}, clear], 'resolve'))
    assert saved.project.facts.builtin_manual_scopes == {scope['cellIds'][1]: scope['id']}
    assert saved.project.facts.manual_scopes[0].raw_input == RAW


def test_delete_undo_and_portable_preserve_historical_scope_without_current_ghosts():
    before, sources = scoped_workspace()
    command, scope = joined_edit(before)
    changed, _ = apply_rich_mutation(before, command)
    current = next(record for record in changed.project.facts.records if record.id == 'employer-a')
    steps = [{'kind': 'remove_record', 'recordId': current.id, 'beforeRevision': current.revision}]
    steps.extend({'kind': 'remove_block', 'blockId': block.id, 'beforeRevision': block.revision}
        for block in changed.project.document.regions[2].blocks)
    deleted, _ = apply_rich_mutation(changed, request(changed, steps, 'delete'))
    assert not deleted.project.facts.builtin_manual_scopes
    assert deleted.project.facts.manual_scopes[0].id == scope['id']
    transferred, _originals, _, _ = open_rich_archive(export_rich_archive(deleted, sources, {}, {}), 'scope-copy')
    assert transferred.project.facts == deleted.project.facts
    inverse = inverse_template_mutation(changed, deleted, origin_action_id='delete',
        mutation_id='undo-delete', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(deleted, inverse, history_authorization=authorization(deleted, inverse))
    assert restored.project.facts.builtin_manual_scopes == changed.project.facts.builtin_manual_scopes
    assert next(record for record in restored.project.facts.records if record.id == current.id).employer.pending_raw_text == RAW


def test_one_scope_can_cover_builtin_and_extension_cells_without_erasing_either():
    before, _sources = scoped_workspace()
    steps, scope = pending_steps(before, names=('employer',))
    extension = before.project.facts.extensions[0].model_copy(deep=True)
    cell = extension.cells[0]
    cell.raw_input, cell.typed_value, cell.state = '', None, 'pending_manual'
    cell.origin, cell.user_corrected, cell.manual_scope_id = 'human', True, scope['id']
    scope['cellIds'].append(cell.id)
    steps.append(extension_step(before, extension))
    changed, _ = apply_rich_mutation(before, request(before, steps, 'joined-edit'))
    assert changed.project.facts.extensions[0].cells[0].manual_scope_id == scope['id']
    assert changed.project.facts.builtin_manual_scopes[scope['cellIds'][0]] == scope['id']
    assert changed.project.facts.manual_scopes[0].cell_ids == scope['cellIds']


def test_period_removal_clears_current_scope_and_undo_restores_exact_period_identity():
    before, _sources = scoped_workspace()
    record = next(record for record in before.project.facts.records if record.id == 'employer-a')
    from packages.resume_core.template_builtin_admission import unknown
    record.periods = [WorkingPeriod(id='exact-period', revision=1, start=unknown(), end=unknown(),
        present=unknown(), evidence=[])]
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    steps, scope = pending_steps(before, names=('period:exact-period:start',))
    pending, _ = apply_rich_mutation(before, request(before, steps, 'joined-edit'))
    current = next(record for record in pending.project.facts.records if record.id == 'employer-a')
    removed = current.model_copy(deep=True)
    removed.periods = []
    deleted, _ = apply_rich_mutation(pending, request(pending, [
        {'kind': 'put_record', 'beforeRevision': current.revision, 'record': removed.model_dump(by_alias=True)}], 'remove-period'))
    assert not deleted.project.facts.builtin_manual_scopes
    assert deleted.project.facts.manual_scopes[0].id == scope['id']
    inverse = inverse_template_mutation(pending, deleted, origin_action_id='remove-period',
        mutation_id='undo-period', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(deleted, inverse, history_authorization=authorization(deleted, inverse))
    current = next(record for record in restored.project.facts.records if record.id == 'employer-a')
    assert current.periods[0].id == 'exact-period'
    assert current.periods[0].start.pending_raw_text == RAW
    assert restored.project.facts.builtin_manual_scopes == pending.project.facts.builtin_manual_scopes


def test_undo_to_legacy_pending_field_without_scope_does_not_fabricate_a_scope():
    before, _sources = scoped_workspace()
    record = next(record for record in before.project.facts.records if record.id == 'employer-a')
    record.employer.status = 'pending'
    record.employer.pending_raw_text = 'Legacy pending wording'
    record.employer.user_corrected = True
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    command, _scope = joined_edit(before)
    changed, _ = apply_rich_mutation(before, command)
    inverse = inverse_template_mutation(before, changed, origin_action_id='joined-edit',
        mutation_id='undo-legacy', session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(changed, inverse, history_authorization=authorization(changed, inverse))
    current = next(record for record in restored.project.facts.records if record.id == 'employer-a')
    assert current.employer.value == 'employer-a'
    assert current.employer.pending_raw_text == 'Legacy pending wording'
    assert not restored.project.facts.builtin_manual_scopes
