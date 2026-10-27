"""Prepared address maps state exact result ownership for later buffered input."""

import json

import pytest

from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.template_address import PreparedAddressMapV1
from packages.resume_core.models.template_authoring import TemplateEditPreparationV1
from packages.resume_core.models.template_document import ManualScopeSpan, PresentedText
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.models.template_writer import WriterPreparedDeltaV2, WriterPreparedEditV2
from packages.resume_core.rich_fields import inline_groups
from packages.resume_core.template_address_map import address_map_sha256, build_address_map
from packages.resume_core.template_preparation import prepare_edit
from packages.resume_core.templates.compiler import canonical, sha256
from packages.resume_core.templates.presentation import snapshot_identity
from tests.templates.address_map_fixtures import (ADDRESS, TRANSPORT, block_of, cases, encoded, field, joined, literal,
    operation_request, text_request, transport)
from tests.templates.storage_fixtures import workspace
from tests.templates.test_panel_preparation import period_workspace, panel, prepared
from tests.templates.test_preparation_store import request as writer_request, save_request, setup
from tests.templates.test_scope_displays import copied_workspace
from tests.templates.test_template_preparation import proof, response


def mapped(value, request):
    prepared = prepare_edit(response(value), request)
    address = build_address_map(response(value), request, prepared)
    check_map(value, prepared.preview.workspace, address, prepared.created_ids)
    return prepared, address


def units(text):
    return len(text.encode('utf-16-le')) // 2


def slice16(text, start, end):
    return text.encode('utf-16-le')[start * 2:end * 2].decode('utf-16-le')


def leaves(content):
    # Independent leaf walk: links contribute their children, other spans themselves.
    result, cursor = [], 0
    for index, span in enumerate(content):
        children = [(index, child_index, child) for child_index, child in enumerate(span.content)] if hasattr(span, 'href') else [(index, None, span)]
        for outer, inner, child in children:
            size = units(child.text)
            result.append({'path': [outer] if inner is None else [outer, inner], 'span': child,
                'owner': span if inner is not None else None, 'start': cursor, 'end': cursor + size})
            cursor += size
    return result


def reference(leaf):
    span, owner = leaf['span'], leaf['owner']
    if span.type == 'fact_field':
        return {'kind': 'field', 'bindingId': span.binding_id, 'occurrenceId': span.occurrence_id,
            'recordId': span.record_id, 'fieldKey': span.field_key, 'cellId': span.cell_id}
    if span.type == 'manual_scope':
        return {'kind': 'manual_scope', 'scopeId': span.scope_id, 'occurrenceId': span.occurrence_id,
            'fragmentId': span.fragment_id}
    if owner is not None and owner.type == 'bound_link':
        bound = owner.label_binding or owner.url_binding
        return {'kind': 'bound_text', 'path': leaf['path'], 'binding': 'label' if owner.label_binding else 'url',
            'recordId': bound.record_id, 'fieldKey': bound.field_key, 'cellId': bound.cell_id,
            'occurrenceId': bound.occurrence_id}
    return {'kind': 'literal', 'path': leaf['path']}


def container(value, ref):
    block = block_of(value, ref['blockId'])
    assert block.revision == ref['revision']
    key = ref.get('cellId') or ref['kind']
    return dict(inline_groups(block))[key]


def mechanical(leaf):
    span, owner = leaf['span'], leaf['owner']
    if span.type == 'fact_field':
        return {'kind': 'field', 'bindingId': span.binding_id} if span.complete else None
    if span.type == 'manual_scope':
        return {'kind': 'manual_scope', 'fragmentId': span.fragment_id}
    return None if owner is not None and owner.type == 'bound_link' else {'kind': 'literal'}


def check_map(before, after, address, created_ids):
    """Verify every map claim against both exact workspaces, as a consumer must."""
    raw = address.model_dump(mode='json', by_alias=True)
    assert PreparedAddressMapV1.model_validate_json(canonical(address)) == address
    assert raw['baseSnapshot'] == snapshot_identity(before).model_dump(mode='json', by_alias=True)
    assert raw['resultSnapshot'] == snapshot_identity(after).model_dump(mode='json', by_alias=True)
    slots = {(op, slot): identifier for op, values in created_ids.items() for slot, identifier in values.items()}
    for entry in raw['containers']:
        output = container(after, entry['output'])
        wire = [span.model_dump(mode='json', by_alias=True) for span in output]
        assert entry['afterContentHash'] == sha256(canonical(wire))
        text = ''.join(leaf['span'].text for leaf in leaves(output))
        assert entry['afterLength'] == units(text)
        if entry['created'] is not None:
            assert slots[(entry['created']['opId'], entry['created']['slot'])] == entry['output']['blockId']
            assert entry['output']['blockId'] not in {block.id for block in before.project.document.blocks()}
        source_leaves, source_text = [], None
        if entry['input'] is not None:
            source = container(before, entry['input'])
            assert entry['beforeContentHash'] == sha256(canonical([span.model_dump(mode='json', by_alias=True) for span in source]))
            source_leaves = leaves(source)
            source_text = ''.join(leaf['span'].text for leaf in source_leaves)
            assert entry['beforeLength'] == units(source_text)
        if entry['correspondence'] == 'none':
            continue
        for region in entry['regions']:
            if region['source'] is not None:
                assert slice16(source_text, region['source']['start'], region['source']['end']) == slice16(
                    text, region['result']['start'], region['result']['end'])
        listed = {}
        for segment in entry['segments']:
            result = segment['result']
            leaf = next(leaf for leaf in leaves(output) if leaf['start'] <= result['start'] and result['end'] <= leaf['end']
                and (result['end'] > result['start']) == (leaf['end'] > leaf['start']) and reference(leaf) == result['span'])
            listed.setdefault((leaf['start'], leaf['end'], json.dumps(result['span'], sort_keys=True)), []).append(
                (result['start'], result['end']))
            assert segment['target'] in (None, mechanical(leaf))
            if segment['source'] is not None:
                base = next(base for base in source_leaves if base['start'] <= segment['source']['start']
                    and segment['source']['end'] <= base['end'] and reference(base) == segment['source']['span'])
                assert base is not None
            identifier = result['span'].get('bindingId') or result['span'].get('fragmentId')
            created = {value for value in slots.values()}
            assert (segment['slot'] is not None) == (identifier in created)
            if segment['slot'] is not None:
                assert slots[(segment['slot']['opId'], segment['slot']['slot'])] == identifier
        for value in entry['boundaries']:
            nonempty = [leaf for leaf in leaves(output) if leaf['end'] > leaf['start']]
            inside = [leaf for leaf in nonempty if leaf['start'] < value['offset'] < leaf['end']]
            left = [leaf for leaf in nonempty if leaf['end'] == value['offset']]
            right = [leaf for leaf in nonempty if leaf['start'] == value['offset']]
            prior = mechanical(inside[0]) if inside else {'kind': 'literal'} if value['offset'] == 0 else mechanical(left[0]) if left else None
            later = mechanical(inside[0]) if inside else {'kind': 'literal'} if value['offset'] == units(text) else mechanical(right[0]) if right else None
            assert value['before'] in (None, prior) and value['after'] in (None, later)
        # Listed pieces tile their whole leaf; every unlisted leaf is the identical base leaf at its mapped position.
        for leaf in leaves(output):
            pieces = sorted(listed.get((leaf['start'], leaf['end'], json.dumps(reference(leaf), sort_keys=True)), []))
            if pieces:
                if leaf['start'] == leaf['end']:
                    assert len(pieces) == 1
                else:
                    assert pieces[0][0] == leaf['start'] and pieces[-1][1] == leaf['end']
                    assert all(left[1] == right[0] for left, right in zip(pieces, pieces[1:]))
                continue
            region = next((region for region in entry['regions'] if region['result']['start'] <= leaf['start']
                and leaf['end'] <= region['result']['end'] and (leaf['end'] > leaf['start'] or region['source'] is not None)), None)
            if region is None:
                continue
            assert region['source'] is not None, 'inserted text must be listed'
            shift = region['source']['start'] - region['result']['start']
            matches = [base for base in source_leaves if base['start'] == leaf['start'] + shift
                and base['end'] == leaf['end'] + shift and base['span'] == leaf['span']]
            assert matches, ('unlisted changed leaf', leaf)


def probe_targets(after, address):
    """Each supplied target is accepted by the actual preparer at its point."""
    count = 0
    for entry in address.model_dump(mode='json', by_alias=True)['containers']:
        if entry['correspondence'] != 'exact' or entry['output']['kind'] != 'content':
            continue
        points = [(value['offset'], value[side]) for value in entry['boundaries'] for side in ('before', 'after')]
        points += [(value['result']['start'], value['target']) for value in entry['segments']]
        for offset, target in points:
            if target is None:
                continue
            request = text_request(after, offset, offset, 'z', target=target, block=entry['output']['blockId'],
                identifier='probe-' + str(count))
            prepared = prepare_edit(response(after), request)
            assert prepared.mutation is not None
            count += 1
    return count


def entries(address):
    return address.model_dump(mode='json', by_alias=True)['containers']


def test_typing_inside_a_field_reports_cut_flanks_new_text_and_both_boundary_sides():
    before = joined()
    prepared, address = mapped(before, text_request(before, 8, 8, target={'kind': 'field', 'bindingId': 'fragment-paper-a'}))
    [entry] = entries(address)
    assert [(region['role'], region['source'], region['result']) for region in entry['regions']] == [
        ('retained_prefix', {'start': 0, 'end': 8}, {'start': 0, 'end': 8}),
        ('inserted', None, {'start': 8, 'end': 9}),
        ('retained_suffix', {'start': 8, 'end': 32}, {'start': 9, 'end': 33})]
    roles = [(value['role'], value['result']['start'], value['result']['end']) for value in entry['segments']]
    assert roles == [('retained_prefix', 3, 8), ('inserted', 8, 9), ('retained_suffix', 9, 16)]
    assert {value['result']['span']['occurrenceId'] for value in entry['segments']} == {'occurrence-paper-a'}
    assert all(value['slot'] is not None for value in entry['segments'])
    assert [value['source']['span']['bindingId'] for value in entry['segments'] if value['source']] == ['fragment-paper-a'] * 2
    inserted = entry['segments'][1]['result']['span']['bindingId']
    boundaries = {value['offset']: value for value in entry['boundaries']}
    assert boundaries[9]['before'] == {'kind': 'field', 'bindingId': inserted}
    assert boundaries[16]['after'] == {'kind': 'literal'} and boundaries[3]['before'] == {'kind': 'literal'}
    assert boundaries[16]['before']['kind'] == 'field'
    assert probe_targets(prepared.preview.workspace, address) >= 8


def test_literal_insertion_at_a_field_edge_keeps_the_field_and_literal_choices_separate():
    before = joined()
    prepared, address = mapped(before, text_request(before, 15, 15, '!', target={'kind': 'literal'}))
    [entry] = entries(address)
    [segment] = [value for value in entry['segments'] if value['role'] == 'inserted']
    assert segment['result']['span']['kind'] == 'literal' and segment['target'] == {'kind': 'literal'}
    boundary = next(value for value in entry['boundaries'] if value['offset'] == 15)
    assert boundary['before'] == {'kind': 'field', 'bindingId': 'fragment-paper-a'}
    assert boundary['after'] == {'kind': 'literal'}
    assert probe_targets(prepared.preview.workspace, address) >= 3


def test_repeated_same_cell_occurrences_remain_independently_addressable():
    before = joined(lambda ref: [field('title', 'a-title', 'first-binding', 'first-occurrence', 'Shared title', ref),
        literal(' = ', ref), field('title', 'a-title', 'second-binding', 'second-occurrence', 'Shared title', ref)])
    prepared, address = mapped(before, text_request(before, 15, 15, 'Q', target={'kind': 'field', 'bindingId': 'second-binding'}))
    [entry] = entries(address)
    inserted = [value for value in entry['segments'] if value['role'] == 'inserted']
    assert [value['result']['span']['occurrenceId'] for value in inserted] == ['second-occurrence']
    first = [value for value in entry['segments'] if value['result']['span'].get('occurrenceId') == 'first-occurrence']
    assert all(value['source']['span']['bindingId'] == 'first-binding' for value in first)
    assert all(value['result']['span']['cellId'] == 'a-title' for value in entry['segments'] if value['result']['span']['kind'] == 'field')
    probe_targets(prepared.preview.workspace, address)


def test_cross_field_replacement_reports_the_new_manual_scope_owner():
    before = joined()
    prepared, address = mapped(before, text_request(before, 10, 22, 'merged'))
    [entry] = entries(address)
    [inserted] = [value for value in entry['segments'] if value['role'] == 'inserted']
    scope = prepared.preview.workspace.project.facts.manual_scopes[-1]
    assert inserted['result']['span']['kind'] == 'manual_scope' and inserted['result']['span']['scopeId'] == scope.id
    assert inserted['slot'] is not None and inserted['target']['kind'] == 'manual_scope'
    boundary = next(value for value in entry['boundaries'] if value['offset'] == 10)
    assert boundary['before']['kind'] == 'field' and boundary['after']['kind'] == 'manual_scope'
    probe_targets(prepared.preview.workspace, address)


def test_repeat_scope_edit_detaches_other_displays_as_exact_ownership_changes():
    before, _sources, copied_id = copied_workspace()
    prepared, address = mapped(before, text_request(before, 1, 4, '!'))
    detached = [value for value in entries(address) if value['output']['blockId'] == copied_id]
    [entry] = detached
    assert entry['correspondence'] == 'exact' and [value['role'] for value in entry['regions']] == ['retained']
    assert entry['segments'] and all(value['source']['span']['kind'] == 'manual_scope'
        and value['result']['span']['kind'] == 'literal' for value in entry['segments'])
    assert isinstance(block_of(prepared.preview.workspace, copied_id).content[0], PresentedText)


def test_deleting_a_whole_field_keeps_an_explicit_empty_anchor_that_typing_can_target():
    before = joined()
    prepared, address = mapped(before, text_request(before, 3, 15, ''))
    [entry] = entries(address)
    anchors = [value for value in entry['segments'] if value['result']['start'] == value['result']['end']]
    assert anchors and anchors[0]['result']['span']['occurrenceId'] == 'occurrence-paper-a'
    target = anchors[0]['target']
    assert target == {'kind': 'field', 'bindingId': anchors[0]['result']['span']['bindingId']}
    after = prepared.preview.workspace
    typed, typed_address = mapped(after, text_request(after, 3, 3, 'New', target=target, identifier='after-anchor'))
    assert ''.join(span.text for span in block_of(typed.preview.workspace, 'block-paper-a').content).startswith('By New / ')
    assert probe_targets(after, address) >= 1


def test_split_names_its_created_block_and_lets_typing_continue_on_both_sides():
    before = joined()
    prepared, address = mapped(before, operation_request(before, {'kind': 'split_block', 'blockId': 'block-paper-a',
        'beforeRevision': 1, 'offset': 8}))
    left, right = entries(address)
    assert left['input'] == right['input'] and left['created'] is None and right['created'] is not None
    assert right['regions'] == [{'role': 'retained_suffix', 'source': {'start': 8, 'end': 32}, 'result': {'start': 0, 'end': 24}}]
    assert prepared.created_ids['op'][right['created']['slot']] == right['output']['blockId']
    after = prepared.preview.workspace
    start = next(value for value in right['boundaries'] if value['offset'] == 0)
    typed, _ = mapped(after, text_request(after, 0, 0, 'Q', target=start['after'], block=right['output']['blockId'],
        identifier='after-split'))
    assert block_of(typed.preview.workspace, right['output']['blockId']).content[0].text.startswith('Q')
    assert probe_targets(after, address) >= 4


def test_merge_maps_both_inputs_into_one_output_without_listing_unchanged_leaves():
    before, _ = workspace()
    prepared, address = mapped(before, operation_request(before, {'kind': 'merge_blocks', 'leadingId': 'block-paper-a',
        'leadingRevision': 1, 'trailingId': 'block-paper-b', 'trailingRevision': 1}))
    first, second = entries(address)
    assert first['output'] == second['output'] and first['input']['blockId'] == 'block-paper-a'
    assert second['regions'][0]['result'] == {'start': 12, 'end': 24} and second['regions'][0]['role'] == 'retained_suffix'


def test_marks_restyle_exact_existing_text_instead_of_inserting_it():
    before = joined()
    prepared, address = mapped(before, text_request(before, 5, 20, kind='set_marks', styles={'bold': True}))
    [entry] = entries(address)
    assert [value['role'] for value in entry['regions']] == ['retained_prefix', 'restyled', 'retained_suffix']
    assert all(value['source'] is not None for value in entry['segments'])
    probe_targets(prepared.preview.workspace, address)


def test_equal_text_replacement_is_the_preparers_restyle_not_new_text():
    before = joined()
    prepared, address = mapped(before, text_request(before, 3, 9, 'Shared', styles={'italic': True}))
    assert [value['role'] for value in entries(address)[0]['regions']][1] == 'restyled'


def test_inserted_paragraph_is_a_created_inserted_output():
    before = joined()
    prepared, address = mapped(before, operation_request(before, {'kind': 'insert_paragraph',
        'contextBlockId': 'block-paper-a', 'contextRevision': 1, 'placement': {'parentId': 'main', 'afterId': 'block-paper-a'},
        'text': 'Fresh'}))
    [entry] = entries(address)
    assert entry['input'] is None and entry['created'] is not None
    assert entry['regions'] == [{'role': 'inserted', 'source': None, 'result': {'start': 0, 'end': 5}}]
    assert entry['segments'][0]['target'] == {'kind': 'literal'}


def test_copied_blocks_have_no_correspondence_but_name_their_created_identity():
    before = joined()
    prepared, address = mapped(before, operation_request(before, {'kind': 'copy_blocks',
        'sources': [{'blockId': 'block-paper-a', 'beforeRevision': 1}], 'placement': {'parentId': 'main', 'afterId': 'block-paper-b'}}))
    [entry] = entries(address)
    assert entry['correspondence'] == 'none' and entry['input'] is None and entry['created'] is not None
    assert not entry['regions'] and not entry['segments'] and not entry['boundaries']


def test_no_op_has_no_containers():
    before = joined()
    prepared, address = mapped(before, text_request(before, 3, 15, 'Shared title'))
    assert prepared.mutation is None and address.containers == [] and address.base_snapshot == address.result_snapshot


def bound(fixture, intent):
    intent.preparation_input_wire = canonical(intent.preparation).decode()
    return intent


def test_retries_full_and_delta_return_the_one_retained_map_and_commit_releases_it(tmp_path):
    fixture = setup(tmp_path)
    intent = bound(fixture, writer_request(fixture, start=2, end=2, text='!', target={'kind': 'field', 'bindingId': 'fragment-paper-a'}))
    first = fixture.writers.prepare_edit(fixture.project, intent)
    assert isinstance(first, WriterPreparedEditV2) and first.address_map_sha256 == address_map_sha256(first.address_map)
    entry = fixture.writers.preparations.openings[fixture.project].entries[intent.preparation.client_mutation_id]
    assert entry.address_map == canonical(first.address_map)
    usage = fixture.writers.preparations.usage()[fixture.project]
    assert usage.draft_bytes >= len(entry.payload) + len(entry.address_map)
    again = fixture.writers.prepare_edit(fixture.project, intent)
    assert canonical(again) == canonical(first)
    unbound = writer_request(fixture, start=2, end=2, text='!', target={'kind': 'field', 'bindingId': 'fragment-paper-a'})
    assert canonical(fixture.writers.prepare_edit(fixture.project, unbound)) == canonical(first.prepared)
    with pytest.raises(BackgroundFailure, match='PREPARATION_RESPONSE_FORM_CONFLICT'):
        fixture.writers.prepare_edit_delta(fixture.project, intent)
    fixture.writers.save(fixture.project, save_request(fixture, first.prepared), originals=fixture.originals)
    entry = fixture.writers.preparations.openings[fixture.project].entries[intent.preparation.client_mutation_id]
    assert entry.address_map is None and entry.payload is None
    with pytest.raises(BackgroundFailure, match='REQUEST_EXPIRED'):
        fixture.writers.prepare_edit(fixture.project, intent)


@pytest.mark.parametrize('form', ['full', 'delta'])
def test_both_response_forms_carry_the_map_of_their_own_preparation(tmp_path, form):
    fixture = setup(tmp_path)
    intent = bound(fixture, writer_request(fixture))
    base = response(fixture.current())
    expected = build_address_map(base, intent.preparation, prepare_edit(base, intent.preparation))
    method = fixture.writers.prepare_edit if form == 'full' else fixture.writers.prepare_edit_delta
    result = method(fixture.project, intent)
    assert isinstance(result, WriterPreparedEditV2 if form == 'full' else WriterPreparedDeltaV2)
    assert canonical(result.address_map) == canonical(expected) and expected.containers
    assert canonical(method(fixture.project, intent)) == canonical(result)


def tamper(address, change):
    value = address.model_dump(mode='json', by_alias=True)
    entry = value['containers'][0]
    if change == 'gap':
        entry['regions'][1]['result']['start'] += 1
    elif change == 'unsorted':
        entry['segments'].reverse()
    elif change == 'boundary':
        entry['boundaries'].pop()
    elif change == 'shift':
        entry['segments'][0]['source']['start'] += 1
    elif change == 'sourced-insert':
        entry['segments'][1]['source'] = dict(entry['segments'][0]['source'])
    elif change == 'none-with-addresses':
        entry['correspondence'] = 'none'
    elif change == 'length':
        entry['afterLength'] += 1
    elif change == 'unchanged':
        value['resultSnapshot'] = value['baseSnapshot']
    return value


@pytest.mark.parametrize('change', ['gap', 'unsorted', 'boundary', 'shift', 'sourced-insert', 'none-with-addresses',
    'length', 'unchanged'])
def test_model_rejects_incoherent_maps(change):
    before = joined()
    _prepared, address = mapped(before, text_request(before, 8, 8, target={'kind': 'field', 'bindingId': 'fragment-paper-a'}))
    with pytest.raises(ValueError):
        PreparedAddressMapV1.model_validate(tamper(address, change))


@pytest.mark.parametrize('change', ['hash', 'request', 'snapshot'])
def test_wrapper_rejects_a_map_for_another_preparation(tmp_path, change):
    fixture = setup(tmp_path)
    result = fixture.writers.prepare_edit_delta(fixture.project, bound(fixture, writer_request(fixture)))
    value = result.model_dump(mode='json', by_alias=True)
    if change == 'hash':
        value['addressMapSha256'] = '0' * 64
    elif change == 'request':
        value['addressMap']['requestHash'] = '1' * 64
        value['addressMapSha256'] = sha256(canonical(value['addressMap']))
    else:
        value['addressMap']['resultSnapshot'] = value['addressMap']['baseSnapshot']
        value['addressMap']['containers'] = []
        value['addressMapSha256'] = sha256(canonical(value['addressMap']))
    with pytest.raises(ValueError):
        WriterPreparedDeltaV2.model_validate(value)


def test_scope_text_inside_one_occurrence_maps_to_its_repeat_fragment():
    before, _sources, _copied = copied_workspace()
    span = block_of(before, 'block-paper-a').content[0]
    assert isinstance(span, ManualScopeSpan)
    prepared, address = mapped(before, text_request(before, 2, 2, 'Z', target={'kind': 'manual_scope', 'fragmentId': span.fragment_id}))
    entry = next(value for value in entries(address) if value['output']['blockId'] == 'block-paper-a')
    inserted = [value for value in entry['segments'] if value['role'] == 'inserted']
    assert inserted and all(value['result']['span']['kind'] == 'manual_scope' for value in inserted)
    probe_targets(prepared.preview.workspace, address)


@pytest.mark.parametrize('cell_id', ['content', 'caption', 'cell-a'])
def test_table_cells_are_cell_containers_even_when_named_like_plain_fields(cell_id):
    from packages.resume_core.models.template_document import TemplateTableBlock
    before = joined()
    old = before.project.document.regions[2].blocks[0]
    table = TemplateTableBlock(type='table', id=old.id, revision=old.revision, props={}, children=[], provenance=[],
        presentation=old.presentation, content={'rows': [{'id': 'row', 'cells': [{'id': cell_id, 'revision': 1,
            'content': old.content}]}], 'columnWidths': [None], 'headerRows': 0, 'headerCols': 0})
    before.project.document.regions[2].blocks[0] = table
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    request = text_request(before, 8, 8, target={'kind': 'field', 'bindingId': 'fragment-paper-a'})
    request.operations[0].range.cell_id = cell_id
    prepared, address = mapped(before, request)
    [entry] = entries(address)
    assert entry['output']['kind'] == entry['input']['kind'] == 'cell' and entry['output']['cellId'] == cell_id
    assert entry['output']['cellRevision'] > entry['input']['cellRevision']
    inserted = next(value for value in entry['boundaries'] if value['offset'] == 9)['before']
    follow = text_request(prepared.preview.workspace, 9, 9, 'Y', target=inserted, identifier='cell-follow')
    follow.operations[0].range.cell_id = cell_id
    assert prepare_edit(response(prepared.preview.workspace), follow).mutation is not None


def test_text_inside_a_plain_link_uses_link_child_paths_and_reports_unsupported_interiors():
    before = joined(lambda ref: [literal('See ', ref), {'type': 'link', 'href': 'https://example.test/x',
        'presentation': ref, 'content': [literal('example page', ref)]}, literal(' now', ref)])
    prepared, address = mapped(before, text_request(before, 6, 10, 'XY'))
    [entry] = entries(address)
    inserted = [value for value in entry['segments'] if value['role'] == 'inserted']
    assert [value['result']['span'] for value in inserted] == [{'kind': 'literal', 'path': [1, 1]}]
    assert inserted[0]['target'] is None
    edges = {value['offset']: value for value in entry['boundaries']}
    assert edges[4]['before'] == {'kind': 'literal'}


def test_bound_label_text_is_addressed_by_path_and_explicit_binding():
    from tests.templates.test_bound_links import linked_workspace
    before, _ = linked_workspace()
    block = before.project.document.regions[2].blocks[0]
    block.content[0].content = [PresentedText(type='text', text='Shared title', styles={}, presentation=block.presentation)]
    before = WorkspaceV7.model_validate(before.model_dump(by_alias=True))
    prepared, address = mapped(before, text_request(before, 0, 6, 'Human'))
    [entry] = entries(address)
    spans = [value['result']['span'] for value in entry['segments']]
    assert spans and all(span['kind'] == 'bound_text' and span['binding'] == 'label' and span['cellId'] == 'a-title'
        and span['occurrenceId'] == 'label-occurrence' for span in spans)
    assert all(value['target'] is None for value in entry['segments'])


def test_checked_in_fixtures_are_reproducible_from_pure_preparation():
    assert ADDRESS.read_text(encoding='utf-8') == encoded(cases())
    assert TRANSPORT.read_text(encoding='utf-8') == encoded(transport())
    reply = WriterPreparedDeltaV2.model_validate_json(json.loads(TRANSPORT.read_text(encoding='utf-8'))['replyWire'])
    assert reply.address_map.containers


def test_review_r1_oversized_exact_output_degrades_to_none_without_rejecting_the_edit(tmp_path):
    before = joined(lambda ref: [literal('x', ref) for _ in range(1001)])
    request = text_request(before, 0, 1001, kind='set_marks', styles={'bold': True})
    prepared, address = mapped(before, request)
    [entry] = entries(address)
    assert prepared.mutation is not None and entry['correspondence'] == 'none' and entry['input'] is not None


def test_review_r1_inline_paste_offers_no_correspondence():
    before = joined()
    request = operation_request(before, {'kind': 'paste_inline', 'destination': {'blockId': 'block-paper-a',
        'beforeRevision': 1, 'cellId': None, 'field': 'content', 'start': 0, 'end': 0,
        'insertionTarget': {'kind': 'literal'}}, 'source': {'kind': 'literal', 'content': [
            {'type': 'text', 'text': 'Pasted', 'styles': {}}]}})
    prepared, address = mapped(before, request)
    assert prepared.mutation is not None and [value['correspondence'] for value in entries(address)] == ['none']


def test_review_r1_unexpected_builder_failure_degrades_one_output(monkeypatch):
    import packages.resume_core.template_address_map as builder
    before = joined()
    original = builder.exact
    def broken(output, specs, created, slot):
        result = original(output, specs, created, slot)
        result[0]['segments'] = list(reversed(result[0]['segments']))
        return result
    monkeypatch.setattr(builder, 'exact', broken)
    _prepared, address = mapped(before, text_request(before, 8, 8, target={'kind': 'field', 'bindingId': 'fragment-paper-a'}))
    assert [value['correspondence'] for value in entries(address)] == ['none']


def test_panel_switch_to_equal_text_has_no_address_correspondence():
    before, _ = period_workspace()
    request = panel(before, values={'period:exact-period:present': '2023'})
    result = prepared(before, request)
    address = build_address_map(response(before), request, result)
    entries = [entry for entry in address.containers if entry.output.block_id == 'period-block']
    assert len(entries) == 1
    entry = entries[0]
    assert entry.correspondence == 'none'
    assert entry.segments == entry.regions == entry.boundaries == []
