"""Human intent wires reject ambiguity and semantic authority from clipboard data."""

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from packages.resume_core.models.template_authoring import (BlockFormatPatch,
    TemplateClipboardCaptureV1, TemplateEditPreparationV1)


SNAPSHOT = {'projectId': 'project', 'projectRevision': 1, 'documentRevision': 2,
    'documentHash': 'a' * 64, 'factsHash': 'b' * 64, 'packageHash': 'c' * 64,
    'presentationHash': 'd' * 64}
CAPTURE = {'sessionId': 'session', 'actionId': 'typing', 'actionToken': 3, 'dependencies': []}
RANGE = {'blockId': 'block', 'beforeRevision': 2, 'cellId': None, 'field': 'content', 'start': 0, 'end': 7}
TARGET = {'blockId': 'block', 'beforeRevision': 2}
PLACEMENT = {'parentId': 'main', 'afterId': 'block'}
OPERATIONS = [
    {'kind': 'replace_text', 'range': RANGE, 'text': 'Exact 😀', 'styles': {'bold': True}},
    {'kind': 'set_marks', 'range': RANGE, 'styles': {'italic': True}},
    {'kind': 'split_block', **TARGET, 'offset': 7},
    {'kind': 'merge_blocks', 'leadingId': 'a', 'leadingRevision': 2, 'trailingId': 'b', 'trailingRevision': 3},
    {'kind': 'insert_paragraph', 'contextBlockId': 'block', 'contextRevision': 2, 'placement': PLACEMENT, 'text': ''},
    {'kind': 'copy_blocks', 'sources': [TARGET], 'placement': PLACEMENT},
    {'kind': 'copy_fragment', 'source': RANGE, 'placement': PLACEMENT},
    {'kind': 'paste_inline', 'destination': RANGE, 'source': {'kind': 'same_project', 'clipboardCaptureId': 'clipboard'}},
    {'kind': 'paste_inline', 'destination': RANGE, 'source': {'kind': 'literal', 'content': [
        {'type': 'link', 'href': 'https://example.test', 'content': [{'type': 'text', 'text': 'Label', 'styles': {}}]}]}},
    {'kind': 'move_block', **TARGET, 'placement': PLACEMENT},
    {'kind': 'remove_occurrences', 'blocks': [TARGET]},
    {'kind': 'delete_entity', 'recordId': 'job', 'beforeRevision': 4},
    {'kind': 'builtin_panel', 'command': {'operation': 'edit', 'recordId': 'job', 'values': {'role': 'Engineer'},
        'factsRevision': 4, 'documentRevision': 2, 'capture': CAPTURE}},
    {'kind': 'format_blocks', 'targets': [TARGET], 'patch': {'blockKind': {'type': 'heading', 'level': 2}, 'alignment': 'left'}},
]


def preparation(operation):
    return {'schemaVersion': 1, 'clientMutationId': 'edit', 'snapshot': deepcopy(SNAPSHOT),
        'capture': deepcopy(CAPTURE), 'operations': [{'opId': 'operation', **deepcopy(operation)}]}


@pytest.mark.parametrize('operation', OPERATIONS, ids=lambda operation: operation['kind'])
def test_all_defined_intents_roundtrip_with_closed_schema(operation):
    model = TemplateEditPreparationV1.model_validate(preparation(operation))
    encoded = model.model_dump(mode='json', by_alias=True)
    assert TemplateEditPreparationV1.model_validate_json(model.model_dump_json(by_alias=True)) == model
    Draft202012Validator(TemplateEditPreparationV1.model_json_schema()).validate(encoded)
    assert encoded['operations'][0]['kind'] == operation['kind']
    assert encoded['capture'] == CAPTURE


@pytest.mark.parametrize('operations', [[], [OPERATIONS[0], OPERATIONS[1]]])
def test_only_one_authored_operation_is_accepted(operations):
    value = preparation(OPERATIONS[0])
    value['operations'] = [{'opId': str(index), **operation} for index, operation in enumerate(operations)]
    with pytest.raises(ValidationError):
        TemplateEditPreparationV1.model_validate(value)


@pytest.mark.parametrize('content', [
    [{'type': 'fact_field', 'bindingId': 'forged', 'recordId': 'job', 'fieldKey': 'role', 'text': 'Engineer', 'styles': {}}],
    [{'type': 'text', 'text': 'Text', 'styles': {}, 'presentation': None}],
    [{'type': 'text', 'text': 'Text', 'styles': {}, 'citations': []}],
    [{'type': 'link', 'href': 'https://example.test', 'content': [{'type': 'bound_link', 'href': 'x', 'content': []}]}],
])
def test_literal_clipboard_cannot_supply_fact_or_presentation_authority(content):
    value = preparation({'kind': 'paste_inline', 'destination': RANGE, 'source': {'kind': 'literal', 'content': content}})
    with pytest.raises(ValidationError):
        TemplateEditPreparationV1.model_validate(value)
    assert list(Draft202012Validator(TemplateEditPreparationV1.model_json_schema()).iter_errors(value))


@pytest.mark.parametrize('patch', [{}, {'alignment': None}, {'blockKind': None},
    {'blockKind': {'type': 'heading', 'level': 4}}, {'blockKind': {'type': 'numbered_list', 'start': 0}}])
def test_empty_null_or_unsupported_block_format_is_rejected(patch):
    with pytest.raises(ValidationError):
        BlockFormatPatch.model_validate(patch)


def test_omitted_format_fields_are_not_encoded_as_explicit_nulls():
    model = BlockFormatPatch.model_validate({'alignment': 'right'})
    assert model.model_dump(by_alias=True) == {'alignment': 'right'}
    assert list(Draft202012Validator(BlockFormatPatch.model_json_schema()).iter_errors({'alignment': None}))


@pytest.mark.parametrize('changes', [{'start': -1}, {'start': 8, 'end': 7}, {'cellId': 'cell', 'field': 'caption'}])
def test_range_rejects_negative_reversed_or_mixed_cell_caption(changes):
    value = preparation(OPERATIONS[0]); value['operations'][0]['range'].update(changes)
    with pytest.raises(ValidationError):
        TemplateEditPreparationV1.model_validate(value)


def test_panel_cannot_replace_the_outer_action_or_document_capture():
    for changes in [{'documentRevision': 3}, {'capture': {**CAPTURE, 'actionId': 'other'}}]:
        value = preparation(OPERATIONS[-2]); value['operations'][0]['command'].update(changes)
        with pytest.raises(ValidationError, match='panel command capture'):
            TemplateEditPreparationV1.model_validate(value)


def test_duplicate_blocks_and_same_block_merge_are_rejected():
    for operation in [{'kind': 'copy_blocks', 'sources': [TARGET, TARGET], 'placement': PLACEMENT},
            {'kind': 'remove_occurrences', 'blocks': [TARGET, TARGET]},
            {'kind': 'format_blocks', 'targets': [TARGET, TARGET], 'patch': {'alignment': 'left'}},
            {'kind': 'merge_blocks', 'leadingId': 'same', 'leadingRevision': 2, 'trailingId': 'same', 'trailingRevision': 2}]:
        with pytest.raises(ValidationError):
            TemplateEditPreparationV1.model_validate(preparation(operation))


def test_clipboard_capture_binds_project_and_original_selection():
    model = TemplateClipboardCaptureV1.model_validate({'schemaVersion': 1, 'clipboardCaptureId': 'clipboard',
        'projectId': 'project', 'sourceSnapshot': SNAPSHOT, 'selection': {'kind': 'range', 'range': RANGE}})
    assert model.selection.range.end == 7
    value = model.model_dump(by_alias=True); value['projectId'] = 'other'
    with pytest.raises(ValidationError, match='another project'):
        TemplateClipboardCaptureV1.model_validate(value)


def test_preparation_bound_precedes_service_acceptance():
    value = preparation({**OPERATIONS[0], 'text': 'x' * (1024 * 1024)})
    with pytest.raises(ValidationError, match='exceeds 1 MiB'):
        TemplateEditPreparationV1.model_validate(value)


def test_panel_creation_context_is_explicit_and_absence_keeps_original_encoding():
    value = preparation(OPERATIONS[-2])
    original = TemplateEditPreparationV1.model_validate(value)
    assert 'placementContext' not in original.model_dump(by_alias=True)['operations'][0]
    value['operations'][0]['placementContext'] = {'contextBlockId': 'selected-section', 'placement': PLACEMENT}
    selected = TemplateEditPreparationV1.model_validate(value)
    assert selected.operations[0].placement_context.context_block_id == 'selected-section'
    Draft202012Validator(TemplateEditPreparationV1.model_json_schema()).validate(selected.model_dump(mode='json', by_alias=True))


@pytest.mark.parametrize('target', [{'kind': 'field', 'bindingId': 'exact-fragment'}, {'kind': 'literal'}])
def test_collapsed_replacement_requires_explicit_insertion_ownership(target):
    value = preparation(OPERATIONS[0]); value['operations'][0]['range']['end'] = 0
    with pytest.raises(ValidationError, match='explicit insertion target'):
        TemplateEditPreparationV1.model_validate(value)
    value['operations'][0]['range']['insertionTarget'] = target
    assert TemplateEditPreparationV1.model_validate(value).operations[0].range.insertion_target.kind == target['kind']


def test_selection_and_marks_cannot_carry_insertion_intent():
    for operation in [OPERATIONS[0], OPERATIONS[1]]:
        value = preparation(operation); value['operations'][0]['range']['insertionTarget'] = {'kind': 'literal'}
        with pytest.raises(ValidationError):
            TemplateEditPreparationV1.model_validate(value)
    value = preparation(OPERATIONS[1]); value['operations'][0]['range'].update(end=0, insertionTarget={'kind': 'literal'})
    with pytest.raises(ValidationError, match='marks have no insertion target'):
        TemplateEditPreparationV1.model_validate(value)
