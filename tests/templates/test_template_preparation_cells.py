"""Raw input preparation never asserts a typed interpretation or reviews humans."""

import pytest

from packages.resume_core.rich_fields import field_key
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.template_preparation_cells import human_cell_steps
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_builtin_scopes import pending_steps, scoped_workspace
from tests.templates.test_template_preparation_ids import allocator
from tests.templates.test_transactions import authorization, request


def forbidden(*_args, **_kwargs):
    pytest.fail('human input must not invoke semantic conversion or template assertions')


@pytest.mark.parametrize('text', ['Exact title', '2026', '', ' Exact 😀\n spacing '])
def test_direct_extension_input_retains_exact_raw_and_clears_typed_authority(text, monkeypatch):
    before, _ = workspace()
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload', forbidden)
    steps = human_cell_steps(before, ['a-title'], text, 'human-edit', ['block-paper-a'], allocator(before))
    changed, _ = apply_rich_mutation(before, request(before, steps))
    cell = changed.project.facts.extensions[0].cells[0]
    assert cell.raw_input == text and cell.typed_value is None
    assert cell.state == 'human_raw' and cell.user_corrected and cell.origin == 'human'
    assert cell.manual_scope_id is None and cell.revision > before.project.facts.extensions[0].cells[0].revision
    assert changed.project.facts.extensions[1] == before.project.facts.extensions[1]
    assert changed.project.document.regions == before.project.document.regions
    assert changed.document_revision == before.document_revision + 1


def test_direct_builtin_input_bypasses_typed_conversion_and_clears_old_shared_reference(monkeypatch):
    before, _ = scoped_workspace()
    pending, _ = pending_steps(before)
    before, _ = apply_rich_mutation(before, request(before, pending, 'joined-edit'))
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload', forbidden)
    monkeypatch.setattr('packages.resume_core.rich_fields.set_text', forbidden)
    cell_id = field_key('employer-a', 'employer')
    steps = human_cell_steps(before, [cell_id], ' Exact company ', 'direct', ['job-label'], allocator(before))
    changed, _ = apply_rich_mutation(before, request(before, steps, 'direct'))
    company = next(record for record in changed.project.facts.records if record.id == 'employer-a')
    assert company.employer.raw_text == ' Exact company '
    assert company.employer.value is None and company.employer.status == 'unresolved'
    assert company.employer.pending_raw_text is None and company.employer.user_corrected
    assert cell_id not in changed.project.facts.builtin_manual_scopes
    role_id = field_key('employer-a', 'role')
    assert changed.project.facts.builtin_manual_scopes[role_id] == before.project.facts.builtin_manual_scopes[role_id]
    assert changed.project.facts.manual_scopes == before.project.facts.manual_scopes


@pytest.mark.parametrize('text', ['Unsplit exact input — value', ''])
def test_mixed_builtin_extension_input_has_one_scope_with_exact_replacement(text, monkeypatch):
    before, _ = scoped_workspace()
    builtin = field_key('employer-a', 'employer')
    extension = before.project.facts.extensions[0].cells[0].id
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload', forbidden)
    monkeypatch.setattr('packages.resume_core.rich_fields.set_text', forbidden)
    first, retry = allocator(before), allocator(before)
    targets = [builtin, extension]
    steps = human_cell_steps(before, targets, text, 'human-edit', ['job-label'], first)
    repeated = human_cell_steps(before, list(reversed(targets)), text, 'human-edit', ['job-label'], retry)
    assert canonical(steps) == canonical(repeated) and first.created_ids == retry.created_ids
    changed, _ = apply_rich_mutation(before, request(before, steps))
    scope = changed.project.facts.manual_scopes[-1]
    assert scope.raw_input == text and scope.cell_ids == sorted(targets)
    company = next(record for record in changed.project.facts.records if record.id == 'employer-a')
    assert company.employer.value is None and company.employer.status == 'pending'
    assert company.employer.pending_raw_text == text and company.employer.raw_text == ''
    cell = changed.project.facts.extensions[0].cells[0]
    assert cell.state == 'pending_manual' and cell.manual_scope_id == scope.id
    assert cell.typed_value is None and cell.raw_input == ''
    assert changed.project.facts.builtin_manual_scopes[builtin] == scope.id
    undo = inverse_template_mutation(before, changed, origin_action_id='human-edit', mutation_id='undo',
        session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(changed, undo, history_authorization=authorization(changed, undo))
    assert next(record for record in restored.project.facts.records if record.id == company.id).employer == next(
        record for record in before.project.facts.records if record.id == company.id).employer.model_copy(update={
            'revision': next(record for record in restored.project.facts.records if record.id == company.id).employer.revision})
    assert restored.project.facts.extensions[0].cells[0].typed_value == before.project.facts.extensions[0].cells[0].typed_value
    assert not restored.project.facts.builtin_manual_scopes


@pytest.mark.parametrize('targets', [[], ['missing'], ['a-title', 'a-title']])
def test_missing_or_duplicate_human_targets_fail_without_allocating_or_mutating(targets):
    before, _ = workspace()
    original = canonical(before)
    ids = allocator(before)
    with pytest.raises(ValueError):
        human_cell_steps(before, targets, 'Exact', 'human-edit', [], ids)
    assert canonical(before) == original and ids.created_ids == {'operation': {}}


def test_ambiguous_occurrences_of_one_cell_keep_one_scope_without_inventing_a_value():
    before, _ = workspace()
    steps = human_cell_steps(before, ['a-title'], 'Exact replacement only', 'human-edit',
        ['block-paper-a'], allocator(before), ambiguous=True)
    changed, _ = apply_rich_mutation(before, request(before, steps))
    cell = changed.project.facts.extensions[0].cells[0]
    scope = changed.project.facts.manual_scopes[-1]
    assert cell.state == 'pending_manual' and cell.typed_value is None
    assert cell.manual_scope_id == scope.id and scope.cell_ids == ['a-title']
    assert scope.raw_input == 'Exact replacement only' and cell.raw_input == ''
