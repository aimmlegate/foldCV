"""Pure text preparation proves complete atomic raw/issue transactions."""

import pytest

from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import FieldOccurrence, ManualScopeSpan, PresentedText
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.template_api import TemplateProjectResponseV1
from packages.resume_core.template_inverse import inverse_template_mutation, semantic
from packages.resume_core.template_preparation import prepare_text_edit
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.templates.presentation import project_presentation, snapshot_identity
from tests.templates.storage_fixtures import workspace
from tests.templates.test_transactions import authorization, issue


def response(value):
    return TemplateProjectResponseV1(schemaVersion=1, workspace=value, snapshot=snapshot_identity(value),
        presentation=project_presentation(value), durability='durable', savedProjectRevision=value.project_revision,
        savedDocumentRevision=value.document_revision, saveError=None, generation=None, identity=None)


def command(value, *, start=0, end=6, text='Human', styles=None, target=None, kind='replace_text'):
    block = value.project.document.regions[2].blocks[0]
    selected = {'blockId': block.id, 'beforeRevision': block.revision, 'cellId': None,
        'field': 'content', 'start': start, 'end': end}
    if target is not None:
        selected['insertionTarget'] = target
    operation = {'kind': kind, 'opId': 'text', 'range': selected, 'styles': styles or {}}
    if kind == 'replace_text':
        operation['text'] = text
    return TemplateEditPreparationV1(schemaVersion=1, clientMutationId='text-edit', snapshot=snapshot_identity(value),
        capture={'sessionId': 'session', 'actionId': 'action', 'actionToken': 1, 'dependencies': []}, operations=[operation])


def test_partial_field_edit_prepares_whole_raw_field_and_issue_retirement_atomically(monkeypatch):
    before, _ = workspace()
    imported = issue('issue-a', 'a-title'); imported.block_ids = ['block-paper-a']
    before.project.import_issues = [imported]
    def forbidden(*_args, **_kwargs):
        pytest.fail('human preparation must not run template assertions or inference')
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload', forbidden)
    original = canonical(before)
    request = command(before)
    prepared = prepare_text_edit(response(before), request)
    assert canonical(before) == original
    block = prepared.preview.workspace.project.document.regions[2].blocks[0]
    assert ''.join(span.text for span in block.content) == 'Human title'
    cell = prepared.preview.workspace.project.facts.extensions[0].cells[0]
    assert cell.raw_input == 'Human title' and cell.typed_value is None and cell.state == 'human_raw'
    assert prepared.preview.workspace.project.import_issues[0].state == 'retired'
    committed, _ = apply_rich_mutation(before, prepared.mutation)
    assert committed == prepared.preview.workspace
    retry = prepare_text_edit(response(before), request)
    assert canonical(prepared) == canonical(retry)
    assert prepared.created_ids == retry.created_ids


@pytest.mark.parametrize('text', ['', 'Exact 😀'])
def test_full_field_replacement_keeps_one_logical_occurrence_and_raw_authority(text):
    before, _ = workspace()
    prepared = prepare_text_edit(response(before), command(before, end=12, text=text))
    block = prepared.preview.workspace.project.document.regions[2].blocks[0]
    assert ''.join(span.text for span in block.content) == text
    assert block.content[0].occurrence_id == 'occurrence-paper-a'
    assert prepared.preview.workspace.project.facts.extensions[0].cells[0].raw_input == text


def test_marks_preserve_cell_values_and_active_issue_lifecycle():
    before, _ = workspace()
    imported = issue('issue-a', 'a-title'); imported.block_ids = ['block-paper-a']
    before.project.import_issues = [imported]
    prepared = prepare_text_edit(response(before), command(before, kind='set_marks', styles={'bold': True}))
    assert prepared.preview.workspace.project.facts == before.project.facts
    assert prepared.preview.workspace.project.import_issues == before.project.import_issues
    block = prepared.preview.workspace.project.document.regions[2].blocks[0]
    assert block.content[0].styles.bold and not block.content[-1].styles.bold
    assert ''.join(span.text for span in block.content) == 'Shared title'


def test_same_text_and_marks_are_noop_without_allocations_or_revision_advance():
    before, _ = workspace()
    prepared = prepare_text_edit(response(before), command(before, text='Shared'))
    assert prepared.mutation is None and prepared.created_ids == {'text': {}}
    assert prepared.preview.workspace == before and prepared.preview.durability == 'durable'


def test_explicit_field_vs_literal_boundary_insertion_has_distinct_ownership():
    before, _ = workspace()
    field = command(before, start=0, end=0, text='New ', target={'kind': 'field', 'bindingId': 'fragment-paper-a'})
    literal = command(before, start=0, end=0, text='New ', target={'kind': 'literal'})
    bound = prepare_text_edit(response(before), field)
    plain = prepare_text_edit(response(before), literal)
    assert bound.preview.workspace.project.facts.extensions[0].cells[0].raw_input == 'New Shared title'
    assert plain.preview.workspace.project.facts == before.project.facts
    assert plain.preview.workspace.project.document.regions[2].blocks[0].content[0].type == 'text'
    assert bound.request_hash != plain.request_hash


def test_field_plus_literal_replacement_keeps_one_cell_pending_without_inventing_a_value():
    before, _ = workspace()
    block = before.project.document.regions[2].blocks[0]
    block.content.append(PresentedText(type='text', text=' — literal', styles={}))
    prepared = prepare_text_edit(response(before), command(before, start=7, end=15, text='Exact replacement'))
    cell = prepared.preview.workspace.project.facts.extensions[0].cells[0]
    scope = prepared.preview.workspace.project.facts.manual_scopes[-1]
    assert cell.state == 'pending_manual' and cell.typed_value is None and cell.manual_scope_id == scope.id
    assert scope.cell_ids == ['a-title'] and scope.raw_input == 'Exact replacement'
    result = prepared.preview.workspace.project.document.regions[2].blocks[0]
    assert ''.join(span.text for span in result.content) == 'Shared Exact replacementliteral'
    inserted = next(span for span in result.content if isinstance(span, ManualScopeSpan) and span.text == 'Exact replacement')
    assert inserted.citations == before.project.facts.extensions[0].cells[0].evidence


@pytest.mark.parametrize('change', ['snapshot', 'revision', 'binding', 'literal_boundary', 'surrogate'])
def test_invalid_captured_range_fails_without_changing_base(change):
    before, _ = workspace()
    request = command(before)
    if change == 'snapshot':
        request.snapshot.project_revision += 1
    elif change == 'revision':
        request.operations[0].range.before_revision += 1
    elif change == 'binding':
        request = command(before, start=0, end=0, text='New', target={'kind': 'field', 'bindingId': 'missing'})
    elif change == 'literal_boundary':
        request = command(before, start=5, end=5, text='New', target={'kind': 'literal'})
    else:
        before.project.document.regions[2].blocks[0].content[0].text = '😀 text'
        request = command(before, start=1, end=2)
    original = canonical(before)
    with pytest.raises((ValueError, RichMutationFailure)):
        prepare_text_edit(response(before), request)
    assert canonical(before) == original


def test_mutated_response_cannot_reuse_its_old_snapshot_claim():
    before, _ = workspace()
    captured = response(before)
    request = command(before)
    captured.workspace.project.document.regions[2].blocks[0].content[0].text = 'Changed without a new claim'
    with pytest.raises(ValueError, match='exact durable base'):
        prepare_text_edit(captured, request)


def test_bound_link_label_edit_keeps_url_binding_and_its_separate_issue():
    from packages.resume_core.models.template_document import BoundLink, FieldRef
    before, _ = workspace()
    block = before.project.document.regions[2].blocks[0]
    span = block.content[0]
    block.content = [BoundLink(type='bound_link', href='https://example.test/retained', content=[span],
        labelBinding=FieldRef(recordId='paper-a', fieldKey='title', cellId='a-title', occurrenceId='occurrence-paper-a'),
        urlBinding=FieldRef(recordId='paper-a', fieldKey='url', cellId='a-url', occurrenceId='url-occurrence'),
        presentation=span.presentation)]
    for identifier, cell in [('title-issue', 'a-title'), ('url-issue', 'a-url')]:
        finding = issue(identifier, cell); finding.block_ids = [block.id]
        before.project.import_issues.append(finding)
    prepared = prepare_text_edit(response(before), command(before))
    result = prepared.preview.workspace.project.document.regions[2].blocks[0]
    assert len(result.content) == 1 and isinstance(result.content[0], BoundLink)
    assert result.content[0].href == 'https://example.test/retained'
    assert result.content[0].url_binding == block.content[0].url_binding
    assert ''.join(part.text for part in result.content[0].content) == 'Human title'
    assert [finding.state for finding in prepared.preview.workspace.project.import_issues] == ['retired', 'active']


def test_cross_cell_replacement_keeps_one_shared_scope_and_untouched_literal_metadata():
    before, _ = workspace()
    first, second = before.project.document.regions[2].blocks
    other = second.content[0].model_copy(deep=True)
    other.binding_id = 'joined-fragment-b'
    other.occurrence_id = other.binding_root_id = 'joined-occurrence-b'
    first.content = [PresentedText(type='text', text='X', styles={}), first.content[0],
        PresentedText(type='text', text=' / ', styles={}), other]
    prepared = prepare_text_edit(response(before), command(before, start=10, end=19, text='X'))
    facts = prepared.preview.workspace.project.facts
    scope = facts.manual_scopes[-1]
    assert scope.cell_ids == ['a-title', 'b-title'] and scope.raw_input == 'X'
    assert all(record.cells[0].state == 'pending_manual' and record.cells[0].typed_value is None for record in facts.extensions)
    result = prepared.preview.workspace.project.document.regions[2].blocks[0]
    assert result.content[0].text == 'X' and result.content[0].citations == []
    inserted = next(span for span in result.content[1:] if isinstance(span, ManualScopeSpan) and span.text == 'X')
    assert inserted.citations
    assert prepared.preview.workspace.project.document.regions[2].blocks[1] == second


@pytest.mark.parametrize('start,end,text', [(0, 6, 'Human'), (0, 12, ''), (0, 12, 'Exact 😀')])
def test_independently_bound_literal_link_label_updates_whole_human_raw_value(start, end, text):
    from tests.templates.test_bound_links import linked_workspace
    before, _ = linked_workspace()
    link = before.project.document.regions[2].blocks[0].content[0]
    link.content = [PresentedText(type='text', text='Shared title', styles={}, presentation=link.presentation)]
    imported = issue('label-issue', 'a-title'); imported.block_ids = ['block-paper-a']
    before.project.import_issues = [imported]
    prepared = prepare_text_edit(response(before), command(before, start=start, end=end, text=text))
    result = prepared.preview.workspace.project.document.regions[2].blocks[0].content[0]
    expected = text + 'Shared title'[end:]
    cell = prepared.preview.workspace.project.facts.extensions[0].cells[0]
    assert cell.state == 'human_raw' and cell.raw_input == expected and cell.typed_value is None
    assert ''.join(part.text for part in result.content) == expected
    assert result.label_binding == link.label_binding and result.url_binding == link.url_binding and result.href == link.href
    assert prepared.preview.workspace.project.facts.extensions[0].cells[3] == before.project.facts.extensions[0].cells[3]
    assert prepared.preview.workspace.project.import_issues[0].state == 'retired'
    assert canonical(prepared) == canonical(prepare_text_edit(response(before), command(before, start=start, end=end, text=text)))


def test_independent_label_literal_parts_belong_to_the_whole_label_occurrence():
    from tests.templates.test_bound_links import linked_workspace
    before, _ = linked_workspace()
    link = before.project.document.regions[2].blocks[0].content[0]
    link.content = [PresentedText(type='text', text='Prefix ', styles={}), link.content[0]]
    prepared = prepare_text_edit(response(before), command(before, start=0, end=6, text='Human'))
    cell = prepared.preview.workspace.project.facts.extensions[0].cells[0]
    assert cell.state == 'human_raw' and cell.raw_input == 'Human Shared title'


@pytest.mark.parametrize('start,end', [(0, 6), (0, 0), (22, 22)])
def test_url_only_text_changes_reject_before_preview(start, end):
    from tests.templates.test_bound_links import linked_workspace
    before, _ = linked_workspace()
    link = before.project.document.regions[2].blocks[0].content[0]
    link.label_binding = None
    span = link.content[0]
    span.field_key, span.cell_id = 'url', 'a-url'
    span.occurrence_id = span.binding_root_id = 'url-occurrence'
    span.text = link.href
    if start == 22:
        start = end = len(span.text)
    target = {'kind': 'field', 'bindingId': span.binding_id} if start == end else None
    original = canonical(before)
    with pytest.raises(ValueError, match='URL-only'):
        prepare_text_edit(response(before), command(before, start=start, end=end, target=target))
    assert canonical(before) == original


def test_bound_label_cannot_be_bypassed_by_literal_insertion_inside_the_link():
    from tests.templates.test_bound_links import linked_workspace
    before, _ = linked_workspace()
    link = before.project.document.regions[2].blocks[0].content[0]
    link.content = [PresentedText(type='text', text='Shared title', styles={})]
    with pytest.raises(ValueError, match='literal boundary'):
        prepare_text_edit(response(before), command(before, start=5, end=5, target={'kind': 'literal'}))


def test_cross_link_replacement_cannot_discard_an_untouched_url_reference():
    from tests.templates.test_bound_links import linked_workspace
    before, _ = linked_workspace()
    before.project.document.regions[2].blocks[0].content.append(PresentedText(type='text', text=' trailing', styles={}))
    with pytest.raises(ValueError, match='untouched URL'):
        prepare_text_edit(response(before), command(before, start=0, end=14))


@pytest.mark.parametrize('start,end,text,target', [(7, 24, 'Changed replacement', None),
    (7, 7, 'New', {'kind': 'literal'}), (7, 24, '', None)])
def test_repeat_edit_of_shared_input_uses_addressed_scope_and_guards_literal_insertion(start, end, text, target):
    before, _ = workspace()
    before.project.document.regions[2].blocks[0].content.append(PresentedText(type='text', text=' — literal', styles={}))
    initial = prepare_text_edit(response(before), command(before, start=7, end=15, text='Exact replacement'))
    saved = initial.preview.workspace
    request = command(saved, start=start, end=end, text=text, target=target)
    request.client_mutation_id = 'second-edit'
    original = canonical(saved)
    if target is not None:
        with pytest.raises(ValueError, match='literal boundary'):
            prepare_text_edit(response(saved), request)
    else:
        prepared = prepare_text_edit(response(saved), request)
        new_scope = prepared.preview.workspace.project.facts.manual_scopes[-1]
        assert new_scope.raw_input == text and new_scope.cell_ids == ['a-title']
        assert new_scope.id != saved.project.facts.manual_scopes[-1].id
    assert canonical(saved) == original


def test_marks_of_shared_raw_text_preserve_exact_pending_scope():
    before, _ = workspace()
    before.project.document.regions[2].blocks[0].content.append(PresentedText(type='text', text=' — literal', styles={}))
    saved = prepare_text_edit(response(before), command(before, start=7, end=15, text='Exact replacement')).preview.workspace
    request = command(saved, start=7, end=24, kind='set_marks', styles={'italic': True})
    request.client_mutation_id = 'second-edit'
    result = prepare_text_edit(response(saved), request).preview.workspace
    assert result.project.facts == saved.project.facts
    assert result.project.facts.manual_scopes[-1].raw_input == 'Exact replacement'


def copied_field(before):
    """A second occurrence of the first paper block's title field, as a block copy leaves it."""
    source = before.project.document.regions[2].blocks[0]
    copy = source.model_copy(deep=True)
    copy.id = 'block-copy'
    for span in copy.content:
        if isinstance(span, FieldOccurrence):
            span.binding_id, span.binding_root_id, span.occurrence_id = 'copy-fragment', 'copy-root', 'copy-root'
    before.project.document.regions[2].blocks.insert(1, copy)
    return WorkspaceV7.model_validate(before.model_dump(by_alias=True)), source, copy


def test_a_direct_edit_of_one_occurrence_turns_its_copies_into_plain_text():
    before, _ = workspace()
    before, source, copy = copied_field(before)
    result = prepare_text_edit(response(before), command(before))
    blocks = {block.id: block for block in result.preview.workspace.project.document.blocks()}
    assert ''.join(span.text for span in blocks[source.id].content).startswith('Human')
    assert [span.type for span in blocks[copy.id].content if span.text] == ['text']
    assert ''.join(span.text for span in blocks[copy.id].content) == ''.join(span.text for span in copy.content)
    changed, _ = apply_rich_mutation(before, result.mutation)
    assert changed == result.preview.workspace
    inverse = inverse_template_mutation(before, changed, origin_action_id=result.mutation.action_id, mutation_id='undo-copy',
        session_id='session', action_token=2)
    restored, _ = apply_rich_mutation(changed, inverse, history_authorization=authorization(changed, inverse))
    assert semantic(restored.project.document) == semantic(before.project.document)


def test_a_copy_in_the_edited_block_goes_plain_with_the_edit():
    before, _ = workspace()
    source = before.project.document.regions[2].blocks[0]
    span = next(value for value in source.content if isinstance(value, FieldOccurrence))
    source.content.append(span.model_copy(update={'binding_id': 'copy-fragment', 'binding_root_id': 'copy-root',
        'occurrence_id': 'copy-root'}, deep=True))
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    result = prepare_text_edit(response(before), command(before))
    changed = next(block for block in result.preview.workspace.project.document.blocks() if block.id == source.id)
    assert [part.type for part in changed.content] == ['fact_field', 'fact_field', 'text']
    assert changed.content[-1].text == span.text
    assert apply_rich_mutation(before, result.mutation)[0] == result.preview.workspace
