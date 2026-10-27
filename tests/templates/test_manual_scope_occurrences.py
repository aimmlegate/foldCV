"""Shared human input has durable occurrence identity without a field assignment."""

import pytest

from packages.resume_core.models.template_document import ManualScopeSpan, PresentedText
from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.archive_zip import write_zip
from packages.resume_core.template_archive import archive_payload_v7, open_archive_v7
from packages.resume_core.rich_dependencies import dependencies_current, dependency
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation, cut_inline
from packages.resume_core.template_authoring import copy_blocks, copy_fragment, copy_inline, merge_blocks, split_block
from packages.resume_core.template_dependencies import selector
from packages.resume_core.template_preparation import prepare_text_edit
from packages.resume_core.template_preparation_cells import human_cell_steps
from packages.resume_core.template_preparation_ids import EditIdAllocator, existing_ids
from packages.resume_core.template_scope_occurrences import active_scope_cells, scope_occurrences
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_template_preparation import command, response


def shared_workspace(text='Exact human input'):
    before, sources = workspace()
    allocator = EditIdAllocator('template-project', 'create-shared', 'scope', existing_ids(before))
    steps = human_cell_steps(before, ['a-title', 'b-title'], text, 'scope-action', ['block-paper-a'], allocator)
    scope = steps[0]['scope']
    block = before.project.document.regions[2].blocks[0].model_copy(deep=True)
    block.content = [ManualScopeSpan(type='manual_scope', scopeId=scope['id'], occurrenceId='shared-occurrence',
        fragmentId='shared-fragment', text=text, styles={}, presentation=block.presentation,
        citations=before.project.facts.extensions[0].cells[0].evidence)]
    steps.append({'kind': 'put_block', 'parentId': 'main', 'afterId': None, 'beforeRevision': 1,
        'block': block.model_dump(by_alias=True), 'keepChildren': True})
    mutation = TemplateMutationV1(schemaVersion=1, projectId=before.project_id, clientMutationId='create-shared',
        actionId='scope-action', kind='typing', capture={'sessionId': 'session', 'actionId': 'scope-action',
            'actionToken': 1, 'dependencies': []}, history={'kind': 'edit', 'originActionId': None}, steps=steps)
    return apply_rich_mutation(before, mutation)[0], sources


@pytest.mark.parametrize('text', ['Exact human input', '', 'Exact 😀\n input'])
def test_shared_occurrence_has_exact_input_and_survives_portable_transfer(text):
    value, sources = shared_workspace(text)
    span = value.project.document.regions[2].blocks[0].content[0]
    assert isinstance(span, ManualScopeSpan) and span.text == text
    assert active_scope_cells(value.project.facts)[span.scope_id] == {'a-title', 'b-title'}
    group = scope_occurrences(value.project.document)[(span.scope_id, span.occurrence_id)]
    assert group.text == text and group.block_ids == ['block-paper-a']
    restored, _, _, _ = open_archive_v7(write_zip(archive_payload_v7(value, sources, {})), 'scope-transfer')
    assert restored.project.document == value.project.document and restored.project.facts == value.project.facts


@pytest.mark.parametrize('change', ['text', 'scope', 'duplicate_fragment', 'foreign_occurrence', 'inactive'])
def test_scope_integrity_rejects_lost_text_identity_or_current_authority(change):
    value, _ = shared_workspace()
    span = value.project.document.regions[2].blocks[0].content[0]
    if change == 'text':
        span.text = 'Different unbound authority'
    elif change == 'scope':
        span.scope_id = 'missing-scope'
    elif change == 'duplicate_fragment':
        copy = span.model_copy(deep=True); copy.occurrence_id = 'copy-root'
        value.project.document.regions[2].blocks[0].content.append(copy)
    elif change == 'foreign_occurrence':
        span.occurrence_id = 'occurrence-paper-b'
    else:
        for record in value.project.facts.extensions:
            cell = record.cells[0]
            cell.state, cell.manual_scope_id, cell.raw_input = 'human_raw', None, 'Changed separately'
    with pytest.raises(ValueError):
        WorkspaceV7.model_validate(value.model_dump(by_alias=True))


def test_complete_scope_copy_has_fresh_display_identity_and_partial_copy_is_literal():
    value, _ = shared_workspace()
    original = value.project.document.regions[2].blocks[0]
    allocator = EditIdAllocator('template-project', 'copy-scoped', 'copy', existing_ids(value))
    copied = copy_blocks(value.project, [original], id_factory=allocator)[0]
    span, source = copied.content[0], original.content[0]
    assert isinstance(span, ManualScopeSpan) and span.scope_id == source.scope_id
    assert span.fragment_id != source.fragment_id and span.occurrence_id != source.occurrence_id
    value.project.document.regions[2].blocks.append(copied)
    WorkspaceV7.model_validate(value.model_dump(by_alias=True))
    partial = copy_fragment(value.project, original, 0, 5).content[0]
    assert isinstance(partial, PresentedText) and partial.text == 'Exact' and partial.citations
    assert not hasattr(partial, 'scope_id')


@pytest.mark.parametrize('shape', ['split_blocks', 'marked_block', 'marked_inline'])
@pytest.mark.parametrize('deterministic', [False, True])
def test_complete_multifragment_scope_copy_freezes_coverage_and_one_new_root(shape, deterministic):
    value, _ = shared_workspace()
    region = value.project.document.regions[2]
    if shape == 'split_blocks':
        region.blocks[0:1] = list(split_block(region.blocks[0], 5))
        selected = region.blocks[:2]
    else:
        value = prepare_text_edit(response(value), command(value, start=2, end=6, kind='set_marks', styles={'bold': True})).preview.workspace
        region = value.project.document.regions[2]
        selected = region.blocks[:1]
    original = canonical(value)
    options = {'id_factory': EditIdAllocator('template-project', 'copy-fragments', 'copy', existing_ids(value))} if deterministic else {}
    if shape == 'marked_inline':
        copied = selected[0].model_copy(deep=True); copied.id = 'inline-copy'
        copied.content = copy_inline(value.project, selected[0].content, **options)
        copies = [copied]
    else:
        copies = copy_blocks(value.project, selected, **options)
    assert canonical(value) == original
    spans = [span for block in copies for span in block.content]
    assert len(spans) > 1 and all(isinstance(span, ManualScopeSpan) for span in spans)
    assert len({span.occurrence_id for span in spans}) == 1
    assert ''.join(span.text for span in spans) == 'Exact human input'
    region.blocks.extend(copies)
    WorkspaceV7.model_validate(value.model_dump(by_alias=True))


def test_empty_scope_occurrence_has_one_exact_zero_length_anchor():
    value, _ = shared_workspace('')
    block = value.project.document.regions[2].blocks[0]
    extra = block.content[0].model_copy(deep=True); extra.fragment_id = 'duplicate-empty-anchor'
    block.content.append(extra)
    with pytest.raises(ValueError, match='exact raw input'):
        WorkspaceV7.model_validate(value.model_dump(by_alias=True))


@pytest.mark.parametrize('offset', [0, 5, 17])
def test_scope_split_merge_preserves_logical_identity_and_exact_text(offset):
    value, _ = shared_workspace()
    block = value.project.document.regions[2].blocks[0]
    allocator = EditIdAllocator('template-project', 'split-scoped', 'split', existing_ids(value))
    left, right = split_block(block, offset, id_factory=allocator)
    value.project.document.regions[2].blocks[0:1] = [left, right]
    validated = WorkspaceV7.model_validate(value.model_dump(by_alias=True))
    group = next(iter(scope_occurrences(validated.project.document).values()))
    assert group.text == 'Exact human input'
    assert len({span.fragment_id for span in group.spans}) == len(group.spans)
    merged = merge_blocks(left, right)
    value.project.document.regions[2].blocks[0:2] = [merged]
    WorkspaceV7.model_validate(value.model_dump(by_alias=True))


def test_manual_partial_cut_needs_an_explicit_allocator_and_retains_empty_anchor():
    value, _ = shared_workspace()
    span = value.project.document.regions[2].blocks[0].content[0]
    with pytest.raises(RichMutationFailure):
        cut_inline([span], 1, 3)
    empty, _ = shared_workspace('')
    block = empty.project.document.regions[2].blocks[0]
    allocator = EditIdAllocator('template-project', 'split-empty', 'split', existing_ids(empty))
    left, right = split_block(block, 0, id_factory=allocator)
    assert left.content == [] and len(right.content) == 1 and right.content[0].fragment_id == 'shared-fragment'


def test_scope_dependency_tracks_active_cells_without_resurrecting_historical_references():
    value, _ = shared_workspace()
    span = value.project.document.regions[2].blocks[0].content[0]
    key = selector('scope_occurrence', canonical([span.scope_id, span.occurrence_id]).decode())
    captured = dependency(value, 'field', key)
    cell = value.project.facts.extensions[0].cells[0]
    cell.state, cell.manual_scope_id, cell.raw_input = 'human_raw', None, 'Separate input'
    assert active_scope_cells(value.project.facts)[span.scope_id] == {'b-title'}
    assert value.project.facts.manual_scopes[0].cell_ids == ['a-title', 'b-title']
    WorkspaceV7.model_validate(value.model_dump(by_alias=True))
    assert not dependencies_current(value, [captured])


def test_marks_preserve_scope_input_and_text_changes_create_new_exact_authority():
    value, _ = shared_workspace()
    prepared = prepare_text_edit(response(value), command(value, start=2, end=6, kind='set_marks', styles={'bold': True}))
    assert prepared.preview.workspace.project.facts == value.project.facts
    group = next(iter(scope_occurrences(prepared.preview.workspace.project.document).values()))
    assert group.text == 'Exact human input' and any(span.styles.bold for span in group.spans)
    changed = prepare_text_edit(response(value), command(value)).preview.workspace
    assert changed.project.facts.manual_scopes[-1].raw_input == 'Humanhuman input'
    assert changed.project.facts.manual_scopes[0] == value.project.facts.manual_scopes[0]


def test_empty_scope_at_selection_start_contributes_current_cells_to_replacement():
    value, _ = shared_workspace('')
    source = value.project.document.regions[2].blocks[0]
    copied = copy_blocks(value.project, [source])[0]
    copied.content.append(PresentedText(type='text', text='X', styles={}))
    value.project.document.regions[2].blocks.append(copied)
    request = command(value, end=1)
    request.operations[0].range.block_id = copied.id
    request.operations[0].range.before_revision = copied.revision
    changed = prepare_text_edit(response(value), request).preview.workspace
    scope = changed.project.facts.manual_scopes[-1]
    assert scope.cell_ids == ['a-title','b-title'] and scope.raw_input == 'Human'
    assert changed.project.document.regions[2].blocks[0].content[0].text == ''
    assert not isinstance(changed.project.document.regions[2].blocks[0].content[0],ManualScopeSpan)


def test_scope_fragments_cannot_be_reordered_as_a_content_preserving_transform():
    value, _ = shared_workspace()
    block = value.project.document.regions[2].blocks[0]
    left, right = split_block(block, 5)
    value.project.document.regions[2].blocks[0:1] = [right, left]
    with pytest.raises(ValueError, match='exact raw input'):
        WorkspaceV7.model_validate(value.model_dump(by_alias=True))


def test_removing_the_only_display_leaves_exact_pending_cells_and_scope_history():
    value, _ = shared_workspace()
    facts = canonical(value.project.facts)
    value.project.document.regions[2].blocks.pop(0)
    WorkspaceV7.model_validate(value.model_dump(by_alias=True))
    assert canonical(value.project.facts) == facts and not scope_occurrences(value.project.document)


@pytest.mark.parametrize('kind', ['link', 'bound_link'])
def test_scope_ownership_cannot_be_nested_inside_link_children(kind):
    value, _ = shared_workspace()
    block = value.project.document.regions[2].blocks[0]
    span = block.content[0].model_dump(mode='json', by_alias=True)
    link = {'type': kind, 'href': 'https://example.test', 'content': [span], 'presentation': None}
    if kind == 'bound_link':
        field = value.project.document.regions[2].blocks[1].content[0]
        link.update(labelBinding=None, urlBinding={'recordId': field.record_id, 'fieldKey': field.field_key,
            'cellId': field.cell_id, 'occurrenceId': field.occurrence_id})
    payload = value.model_dump(mode='json', by_alias=True)
    payload['project']['document']['regions'][2]['blocks'][0]['content'] = [link]
    with pytest.raises(ValueError):
        WorkspaceV7.model_validate(payload)
