"""Named semantic feedback alone authorizes captured primary/fallback repair slots."""

import pytest

from packages.resume_core.models.template_import import ReferenceTable
from packages.resume_core.template_completion import complete_reply
from packages.resume_core.template_identity import capture_span, evidence_options, line_spans
from packages.resume_core.template_import import spent_calls
from tests.templates.generic_fixtures import generic_package, job
from tests.templates.storage_fixtures import source_fixture
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.test_template_pipeline import failing_review
from resume_api.providers.content import ContentFailure


@pytest.mark.asyncio
@pytest.mark.parametrize('repair', ['primary', 'fallback', 'fallback_failure', 'fallback_unavailable', 'no_fallback'])
async def test_repairs_keep_siblings_and_use_only_configured_slots(tmp_path, repair):
    fixture = RuntimeFixture(tmp_path, fallback=repair != 'no_fallback')
    rejected, reviews, models = [], [], []
    def script(request, value):
        models.append(request.policy.model)
        if 'targets' in value:
            reviews.append(value)
            if not rejected:
                rejected.extend(allocation['cellIds']['journal'] for allocation in value['handleMap'] if allocation['key'] == 'b')
            fail = len(reviews) == 1 or repair == 'fallback_failure'
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
                'disposition': 'violation' if fail and target['targetId'] in rejected else 'satisfied',
                'reason': 'Journal is not supported by source' if fail and target['targetId'] in rejected else '',
                'actionable': fail and target['targetId'] in rejected, 'evidence': []} for target in value['targets']]}
        result = raw_proposal(fixture.source)
        if value['slot'] == 'initial':
            result['payload'][1]['journal'] = 'Invented journal'
            return result
        assert value['feedback'] and all(item['ruleId'] and item['targetId'] and item['reason'] for item in value['feedback'])
        if repair in {'fallback', 'fallback_unavailable', 'no_fallback'} and value['slot'] == 'primary_repair':
            return '{invalid primary repair'
        if repair == 'fallback_unavailable' and value['slot'] == 'fallback_repair':
            raise ContentFailure('MODEL_DENIED', logical_attempts=0, cleanup_verified=True,
                dispatch_witness={'transport': 'controlled', 'neverDispatched': True})
        handles = {allocation['key']: allocation['itemHandle'] for allocation in value['capturedHandles']}
        result['discoveries'], result['lineage'] = [], []
        for field in result['fields']:
            field['item'] = {'kind': 'handle', 'itemHandle': handles[field['item']['key']]}
        if repair == 'fallback_failure':
            # A reworded journal is the model's to check; the verbatim one would be settled by the coordinator (D115).
            result['payload'][1]['journal'] = 'Queue Review Quarterly'
        return result
    fixture.transport.scripted = script
    operation = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert operation.state == 'published' and len(operation.allocations) == 2
    assert spent_calls(operation) == len(fixture.transport.calls) - (repair == 'fallback_unavailable')
    facts = fixture.current().project.facts
    assert len(facts.extensions) == 2
    assert facts.extensions[0].cells[0].revision == 1
    assert next(value for value in facts.observations if value.typed_value == 'Invented journal').admission == 'rejected'
    if repair in {'primary', 'fallback'}:
        assert not operation.issues and operation.tasks[0].state == 'accepted'
        assert next(cell for record in facts.extensions for cell in record.cells if cell.id == rejected[0]).typed_value == 'Queue Review'
        assert len(operation.receipts) == 2 and reviews[0] != reviews[-1]
        assert len(fixture.transport.calls) == (4 if repair == 'primary' else 5)
        # D115: the replacement review reuses the first receipt for what the repair left as it was; the corrected
        # journal is verbatim in the source, so the model is asked about the coverage of the block alone.
        settled = operation.review_inputs[-1].value.settled
        assert {value.origin for value in settled} == {'reused', 'verbatim'}
        assert [target['targetId'] for target in reviews[-1]['targets'] if (target['ruleId'], target['targetId'])
            not in {(value.rule_id, value.target_id) for value in settled}] == ['scope-' + operation.tasks[0].id]
    else:
        assert operation.issues and operation.tasks[0].state == 'accepted'
        assert operation.task_results[0].disposition == 'source_fallback'
        assert rejected[0] not in {cell.id for record in facts.extensions for cell in record.cells}
        assert len(fixture.transport.calls) == (3 if repair == 'no_fallback' else 4 if repair == 'fallback_unavailable' else 6)
        if repair == 'fallback_unavailable':
            assert operation.attempts[-1].state == 'released' and operation.cleanup_records[-1].never_dispatched
    assert ('synthetic-fallback' in models) == (repair in {'fallback', 'fallback_failure', 'fallback_unavailable'})


@pytest.mark.asyncio
@pytest.mark.parametrize('cap', [3, 4])
async def test_a_repair_starts_only_when_its_replacement_review_fits_the_cap(tmp_path, cap):
    fixture = RuntimeFixture(tmp_path, cap=cap, fallback=False)
    reviews = []
    def script(_request, value):
        if 'targets' in value:
            reviews.append(value)
            rejected = {allocation['cellIds']['journal'] for allocation in value['handleMap'] if allocation['key'] == 'b'}
            fail = len(reviews) == 1
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'],
                'disposition': 'violation' if fail and target['targetId'] in rejected else 'satisfied',
                'reason': 'Journal is not supported by source' if fail and target['targetId'] in rejected else '',
                'actionable': fail and target['targetId'] in rejected, 'evidence': []} for target in value['targets']]}
        result = raw_proposal(fixture.source)
        if value['slot'] == 'initial':
            result['payload'][1]['journal'] = 'Invented journal'
            return result
        handles = {allocation['key']: allocation['itemHandle'] for allocation in value['capturedHandles']}
        result['discoveries'], result['lineage'] = [], []
        for field in result['fields']:
            field['item'] = {'kind': 'handle', 'itemHandle': handles[field['item']['key']]}
        return result
    fixture.transport.scripted = script
    operation = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert operation.state == 'published'
    if cap == 3:
        # The third call could not be reviewed, so it is not spent.
        assert spent_calls(operation) == 2 and [attempt.slot for attempt in operation.attempts] == ['initial', 'review']
        # The review admitted the other cells, so the block stays accepted and the cap is only a diagnostic.
        assert operation.tasks[0].state == 'accepted' and operation.task_results[0].disposition == 'source_fallback'
        assert 'IMPORT_CALL_CAP' in operation.task_results[0].value['diagnostics']
        assert not operation.issues[0].message.startswith('Показан исходный текст')
    else:
        assert spent_calls(operation) == 4 and operation.tasks[0].state == 'accepted' and not operation.issues


def short_form(payload):
    """A whole reply as the protocol allows it: word-for-word values have no entry and no item is named."""
    return {'schemaVersion': 3, 'payload': payload, 'discoveries': None, 'fields': [], 'lineage': None, 'relations': None}


@pytest.mark.asyncio
async def test_a_repair_without_item_refs_corrects_the_items_it_resends(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    reviews = []
    def script(_request, value):
        if 'targets' in value:
            reviews.append(value)
            journal = {allocation['cellIds']['journal'] for allocation in value['handleMap'] if allocation['key'] == 'b'}
            return failing_review(value, [target for target in value['targets'] if target['targetId'] in journal]
                if len(reviews) == 1 else [])
        result = raw_proposal(fixture.source)
        if value['slot'] == 'initial':
            result['payload'][1]['journal'] = 'Invented journal'
            return result
        return short_form(result['payload'])
    fixture.transport.scripted = script
    operation = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert [attempt.slot for attempt in operation.attempts] == ['initial', 'review', 'primary_repair', 'replacement_review']
    assert operation.proposals[1].applied_receipt_id is not None and not operation.issues
    assert len(operation.allocations) == 2
    extensions = fixture.current().project.facts.extensions
    assert sorted(cell.typed_value for record in extensions for cell in record.cells if cell.field_key == 'journal') == [
        'Queue Review', 'Systems Notes']
    # L03-06: the years stand in the source as digits, so a repair loses neither with a false notice.
    assert not operation.proposals[1].dropped_values
    assert sorted(cell.typed_value for record in extensions for cell in record.cells if cell.field_key == 'year') == [2024, 2025]


def terms_repair(names, fields=(), previous=('Python', 'Perl', 'Docker'), **parts):
    """A programming-block repair over an earlier reply whose items H1, H2 and H3 hold the previous names."""
    package, src = generic_package(), source_fixture('F10')[0]
    block = next(value for value in package.definition.blocks if value.id == 'programming')
    semantic = block.bindings[0].semantic_type
    references = ReferenceTable.model_validate({'items': [{'ref': 'H' + str(index + 1), 'itemHandle': 'item-' + str(index),
        'semanticType': semantic, 'key': None} for index in range(len(previous))], 'cells': [], 'relations': []})
    unit = src.units[0]
    options = evidence_options([capture_span(src, unit), *line_spans(src, unit)], [src])
    return complete_reply({**short_form({'items': list(names)}), 'fields': list(fields), **parts}, block.bindings,
        {option.ref: option for option in options}, references, previous={'payload': {'items': list(previous)}, 'fields': [
            {'pointer': '/items/' + str(index), 'item': 'H' + str(index + 1), 'evidence': []} for index in range(len(previous))]})


def named_items(reply):
    return [field['item'].get('ref') or field['item'].get('key') for field in reply['fields']]


def test_a_repair_item_keeps_the_item_at_its_place_and_a_new_place_adds_one():
    assert named_items(terms_repair(['Python', 'Perl', 'Docker'])) == ['H1', 'H2', 'H3']
    # A corrected value stays its item; replacement, not addition.
    corrected = terms_repair(['Python', 'PostgreSQL', 'Docker'])
    assert named_items(corrected) == ['H1', 'H2', 'H3'] and not corrected['discoveries'] and not corrected['lineage']
    added = terms_repair(['Python', 'Perl', 'Docker', 'PostgreSQL'])
    assert named_items(added)[:3] == ['H1', 'H2', 'H3'] and len(added['discoveries']) == 1
    assert added['lineage'][0]['children'] == [added['discoveries'][0]['key']]
    # The last items left out moved nothing.
    assert named_items(terms_repair(['Python', 'Perl'])) == ['H1', 'H2']


def test_a_discovery_the_repair_names_is_no_second_copy_unless_a_split_asks_for_it():
    discovery = {'key': 'copy', 'semanticType': generic_semantic('programming'), 'pointer': '/items/0'}
    add = {'kind': 'add', 'parents': [], 'children': ['copy']}
    entry = {'pointer': '/items/0', 'item': {'kind': 'discovery_key', 'key': 'copy'}, 'fieldKey': None,
        'evidence': [], 'effectiveCells': None}
    assert named_items(terms_repair(['Python'], [entry], discoveries=[discovery], lineage=[add]))[0] == 'H1'
    split = {'kind': 'split', 'parents': ['H1'], 'children': ['copy']}
    assert named_items(terms_repair(['Python'], [entry], discoveries=[discovery], lineage=[split]))[0] == 'copy'


def generic_semantic(block_id):
    return next(value for value in generic_package().definition.blocks if value.id == block_id).bindings[0].semantic_type


@pytest.mark.parametrize('names', [['Perl', 'Docker'], ['Python', 'Docker'], ['Docker']])
def test_a_repair_that_leaves_an_item_out_and_moves_the_rest_is_refused_by_name(names):
    # Bound by place, the moved item would take its neighbour's handle and its own would stay beside it as a copy.
    with pytest.raises(ValueError, match='does not line up with previousReply'):
        terms_repair(names)


def test_a_repair_that_gives_an_item_to_another_place_is_refused_when_the_rest_name_no_item():
    moved = {'pointer': '/items/0', 'item': {'kind': 'handle', 'ref': 'H3'}, 'fieldKey': None, 'evidence': [], 'effectiveCells': None}
    with pytest.raises(ValueError, match='at /items/2 does not line up'):
        terms_repair(['Docker', 'Perl', 'Python'], [moved])


def jobs_repair(fields):
    package, src = generic_package(), source_fixture('F10')[0]
    block = next(value for value in package.definition.blocks if value.id == 'projects')
    kinds = {'employment': next(binding.semantic_type for binding in block.bindings if binding.pointer == '/*/company')}
    kinds['technology'] = next(binding.semantic_type for binding in block.bindings if binding.pointer.endswith('/technologies/*/display'))
    references = ReferenceTable.model_validate({'items': [{'ref': ref, 'itemHandle': ref.lower(), 'semanticType': kinds[kind], 'key': None}
        for ref, kind in [('H1', 'employment'), ('H2', 'technology'), ('H3', 'employment'), ('H4', 'technology')]],
        'cells': [], 'relations': []})
    unit = src.units[0]
    options = evidence_options([capture_span(src, unit), *line_spans(src, unit)], [src])
    def payload(*order):
        return [job(company, None, None, technologies=[name]) for company, name in order]
    previous = {'payload': payload(('Old Systems', 'Perl'), ('Example Labs', 'Python')), 'fields': [
        {'pointer': '/0/company', 'item': 'H1', 'evidence': []}, {'pointer': '/0/technologies/0/display', 'item': 'H2', 'evidence': []},
        {'pointer': '/1/company', 'item': 'H3', 'evidence': []}, {'pointer': '/1/technologies/0/display', 'item': 'H4', 'evidence': []}]}
    return complete_reply({**short_form(payload(('Example Labs', 'Python'), ('Old Systems', 'Perl'))), 'fields': fields}, block.bindings,
        {option.ref: option for option in options}, references, previous=previous)


def test_values_under_an_item_named_at_another_place_are_refused_rather_than_given_the_place_they_stand_on():
    def named(pointer, ref):
        return {'pointer': pointer, 'item': {'kind': 'handle', 'ref': ref}, 'fieldKey': None, 'evidence': [], 'effectiveCells': None}
    with pytest.raises(ValueError, match='at /0/technologies/0 does not line up'):
        jobs_repair([named('/0/company', 'H3'), named('/1/company', 'H1')])
    # With every item named nothing is left to the place.
    done = jobs_repair([named('/0/company', 'H3'), named('/1/company', 'H1'), named('/0/technologies/0/display', 'H4'),
        named('/1/technologies/0/display', 'H2')])
    assert not done['discoveries']
