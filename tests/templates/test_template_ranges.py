"""Compact V7 ranges consume exact server-allocated flank identities."""

import pytest

from packages.resume_core.models.template_document import PresentedText
from packages.resume_core.models.rich_document import SourceWitness
from packages.resume_core.models.template_mutations import TemplateMutationV1
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from packages.resume_core.template_preparation import prepare_text_edit
from packages.resume_core.templates.compiler import canonical
from tests.templates.storage_fixtures import workspace
from tests.templates.test_template_preparation import command, proof, response


def test_partial_field_range_has_exact_flanks_and_never_allocates_during_application(monkeypatch):
    before, _ = workspace()
    prepared = prepare_text_edit(response(before), command(before, start=3, end=8), proof())
    step = prepared.mutation.steps[0]
    assert step.kind == 'replace_inline_range' and (step.start, step.end) == (3, 8)
    assert len(step.content) == 1 and step.content[0].text == 'Human'
    assert {(entry.source.binding_id, entry.source_start, entry.source_end, entry.role) for entry in step.flank_bindings} == {
        ('fragment-paper-a', 0, 3, 'prefix'), ('fragment-paper-a', 8, 12, 'suffix')}
    def forbidden():
        pytest.fail('a prepared range cannot allocate hidden engine IDs')
    monkeypatch.setattr('packages.resume_core.rich_mutations.uuid.uuid4', forbidden)
    one, _ = apply_rich_mutation(before, prepared.mutation)
    two, _ = apply_rich_mutation(before, prepared.mutation)
    assert canonical(one) == canonical(two) == canonical(prepared.preview.workspace)
    reported = set(prepared.created_ids['text'].values())
    assert {entry.fragment_id for entry in step.flank_bindings} <= reported
    result = one.project.document.regions[2].blocks[0].content
    assert {span.binding_root_id for span in result} == {'occurrence-paper-a'}
    assert {span.cell_id for span in result} == {'a-title'}


@pytest.mark.parametrize('change', ['missing', 'surplus', 'descriptor', 'duplicate_descriptor', 'duplicate_id', 'existing_id', 'replacement_id', 'source_kind'])
def test_missing_surplus_or_colliding_flanks_reject_without_mutating_base(change):
    before, _ = workspace()
    prepared = prepare_text_edit(response(before), command(before, start=3, end=8), proof())
    value = prepared.mutation.model_dump(by_alias=True)
    bindings = value['steps'][0]['flankBindings']
    if change == 'missing':
        bindings.clear()
    elif change == 'surplus':
        extra = {**bindings[0], 'sourceStart': 1, 'fragmentId': 'unused-fresh-fragment'}
        bindings.append(extra)
    elif change == 'descriptor':
        bindings[0]['sourceStart'] = 1
    elif change == 'duplicate_descriptor':
        bindings.append({**bindings[0], 'fragmentId': 'another-fresh-fragment'})
    elif change == 'duplicate_id':
        bindings[0]['fragmentId'] = bindings[1]['fragmentId']
    elif change == 'existing_id':
        bindings[0]['fragmentId'] = 'a-title'
    elif change == 'replacement_id':
        bindings[0]['fragmentId'] = value['steps'][0]['content'][0]['bindingId']
    else:
        bindings[0]['source'] = {'kind': 'manual_scope', 'fragmentId': 'fragment-paper-a'}
    original = canonical(before)
    with pytest.raises(RichMutationFailure):
        apply_rich_mutation(before, TemplateMutationV1.model_validate(value))
    assert canonical(before) == original


def test_nested_link_cut_coordinates_are_local_and_preserve_whole_link_metadata(monkeypatch):
    from tests.templates.test_bound_links import linked_workspace
    before, _ = linked_workspace()
    prepared = prepare_text_edit(response(before), command(before, start=3, end=8), proof())
    step = prepared.mutation.steps[0]
    assert len(step.content) == 1 and step.content[0].type == 'bound_link'
    assert ''.join(span.text for span in step.content[0].content) == 'Human'
    original = before.project.document.regions[2].blocks[0].content[0]
    def forbidden():
        pytest.fail('nested flank IDs must come from the prepared mapping')
    monkeypatch.setattr('packages.resume_core.rich_mutations.uuid.uuid4', forbidden)
    after, _ = apply_rich_mutation(before, prepared.mutation)
    links = after.project.document.regions[2].blocks[0].content
    assert len(links) == 1 and links[0].href == original.href
    assert links[0].label_binding == original.label_binding and links[0].url_binding == original.url_binding
    assert canonical(after) == canonical(prepared.preview.workspace)


def test_literal_one_character_range_omits_large_provenance_and_unrelated_resume():
    before, _ = workspace()
    block = before.project.document.regions[2].blocks[0]
    block.content = [PresentedText(type='text', text='Hi', styles={}, presentation=block.presentation)]
    block.provenance = [SourceWitness(kind='source', id='large-witness', evidence=[{'sourceId': 'source-papers',
        'sourceRevision': 1, 'unitId': 'unit-papers', 'unitRevision': 1, 'text': 'x' * (1024 * 1024)}])]
    wire = before.model_dump(by_alias=True)
    blocks = wire['project']['document']['regions'][2]['blocks']
    for index in range(120):
        blocks.append({**blocks[0], 'id': 'unrelated-' + str(index), 'provenance': [],
            'content': [{'type': 'text', 'text': 'Unrelated text ' + 'z' * 10000, 'styles': {}}]})
    before = WorkspaceV7.model_validate(wire)
    assert len(canonical(before.project.document)) > 2 * 1024 * 1024
    prepared = prepare_text_edit(response(before), command(before, start=2, end=2, text='!', target={'kind': 'literal'}), proof())
    mutation_wire = canonical(prepared.mutation)
    assert len(mutation_wire) < 2000 and len(prepared.mutation.steps) == 1
    step = prepared.mutation.steps[0]
    assert step.flank_bindings == [] and (step.start, step.end) == (2, 2)
    for forbidden in [b'provenance', b'large-witness', b'unrelated-', b'Unrelated text', b'"regions"', b'"records"']:
        assert forbidden not in mutation_wire
    assert prepared.preview.workspace.project.document.regions[2].blocks[0].provenance == before.project.document.regions[2].blocks[0].provenance
    assert prepared.preview.workspace.project.facts == before.project.facts
