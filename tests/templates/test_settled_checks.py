"""D115: the coordinator settles the checks of verbatim values and, in a replacement review, of what a repair left as
it was; the model is asked about the rest, and the receipt still covers every target."""

import json

import pytest

from packages.resume_core.models.template_import import ReviewInput, ReviewInputRecord
from packages.resume_core.template_import import digest, dispatch_attempt, record_return, reserve_attempt
from packages.resume_core.template_prompt import model_prompt
from packages.resume_core.template_proposals import parse_proposal
from packages.resume_core.template_review import decide_review, make_review_input, record_review, validate_review_reply
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.projection import SchemaFailure
from packages.resume_core.templates.replies import check_references, model_targets, review_schema
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.evidence_references import by_reference
from tests.templates.pipeline_fixtures import NOW, cleaned, owner, usage
from tests.templates.storage_fixtures import package
from tests.templates.test_builtin_admission import proposed_from
from tests.templates.test_semantic_admission import proposed, raw_proposal, review_attempt


def by_field(value, allocations):
    """Field key of every settled target, with its origin, by paper key."""
    cells = {cell: (allocation.key, field) for allocation in allocations for field, cell in allocation.cell_ids.items()}
    return {(cells[check.target_id], check.origin) for check in value.settled if check.target_id in cells}


def rewriting_package(fields):
    config = package().definition.model_dump(mode='json', by_alias=True)
    config['blocks'][0]['rewrite'] = {'fields': fields, 'instructions': ['Shorten the title.']}
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def test_verbatim_string_values_are_settled_and_the_model_is_asked_about_the_rest():
    operation, _facts, proposal, captured, source = proposed()
    value = make_review_input(operation, proposal, captured, [source], operation.capture.primary,
        effective_cells=[], semantic_context={'capturedTaskInput': operation.task_inputs[0].value})
    # Title, journal and url stand word for word in the source; the category and the year are not strings.
    assert by_field(value, operation.allocations) == {((key, field), 'verbatim') for key in ['a', 'b'] for field in ['title', 'journal', 'url']}
    asked = model_targets(value)
    assert len(asked) + len(value.settled) == len(value.targets)
    assert {target.target_id.split('-')[0] for target in asked} == {'cell', 'scope'}
    assert all(check.disposition == 'satisfied' and not check.evidence and not check.reason for check in value.settled)
    # The schema and the prompt name only the model's checks; the settled list itself is not sent.
    assert review_schema(value)['$defs']['CheckRef']['enum'] == list(check_references(value))
    prompt = model_prompt(value.model_dump(mode='json', by_alias=True))
    assert '"settled"' not in prompt and prompt.count('"checks":{') == len({target.target_id for target in asked})
    assert 'settled already' in json.dumps(value.semantic_context['replyProtocol'])
    # An input without settled checks keeps its earlier wire form and hash.
    plain = value.model_copy(update={'settled': []})
    assert 'settled' not in plain.model_dump(mode='json', by_alias=True)
    assert digest(ReviewInput.model_validate(plain.model_dump(mode='json', by_alias=True))) == digest(plain)


def test_a_settled_check_cannot_be_answered_and_the_receipt_covers_every_target():
    operation, _facts, proposal, captured, source = proposed()
    operation, attempt, value, _results = review_attempt(operation, proposal, package=captured, source=source)
    operation, receipt = record_review(operation, attempt, [source], NOW)
    assert [(result.rule_id, result.target_id) for result in receipt.reply.results] == [
        (target.rule_id, target.target_id) for target in value.targets]
    assert all(result.disposition == 'satisfied' for result in receipt.reply.results)
    assert set(decide_review(value, receipt, proposal).admitted_cell_ids) == {
        cell for allocation in operation.allocations for cell in allocation.cell_ids.values()}
    beyond = 'C' + str(len(model_targets(value)) + 1)
    with pytest.raises(SchemaFailure):
        validate_review_reply({'results': [{'check': beyond, 'disposition': 'violation', 'reason': 'x', 'evidence': [],
            'actionable': True}]}, value, [source])


@pytest.mark.parametrize('rewrite', [True, False])
def test_a_rewritten_field_is_settled_only_when_rewriting_is_off(rewrite):
    from tests.templates.storage_fixtures import source as source_fixture
    src, _raw = source_fixture()
    operation, _facts, proposal, captured, source = proposed_from(rewriting_package(['/*/title']), src,
        raw_proposal(src), allow_text_rewrite=rewrite)
    value = make_review_input(operation, proposal, captured, [source], operation.capture.primary,
        effective_cells=[], semantic_context={'capturedTaskInput': operation.task_inputs[0].value})
    settled = {field for (_key, field), _origin in by_field(value, operation.allocations)}
    assert settled == ({'journal', 'url'} if rewrite else {'title', 'journal', 'url'})


def test_a_reworded_value_stays_with_the_model():
    from tests.templates.storage_fixtures import source as source_fixture
    src, _raw = source_fixture()
    reply = raw_proposal(src)
    reply['payload'][0]['title'] = 'Reliable queue systems'
    operation, _facts, proposal, captured, source = proposed_from(package(), src, reply)
    value = make_review_input(operation, proposal, captured, [source], operation.capture.primary,
        effective_cells=[], semantic_context={'capturedTaskInput': operation.task_inputs[0].value})
    assert (('a', 'title'), 'verbatim') not in by_field(value, operation.allocations)
    assert (('b', 'title'), 'verbatim') in by_field(value, operation.allocations)


def test_a_replacement_review_reuses_the_receipt_for_what_the_repair_left_as_it_was():
    operation, facts, proposal, captured, source = proposed()
    failing = operation.allocations[1].cell_ids['status']
    operation, attempt, first_value, _results = review_attempt(operation, proposal, package=captured, source=source,
        fail_target=failing)
    operation, first_receipt = record_review(operation, attempt, [source], NOW)
    # The repair updates the captured items by handle, as a live repair does: it rewords paper a's title and leaves
    # everything else, the rejected category included, as it was.
    repair = raw_proposal(source)
    repair['payload'][0]['title'] = 'Reliable queue systems'
    handles = {allocation.key: allocation.item_handle for allocation in operation.allocations}
    repair['discoveries'], repair['lineage'] = [], []
    for field in repair['fields']:
        field['item'] = {'kind': 'handle', 'itemHandle': handles[field['item']['key']]}
    task = operation.tasks[0]
    operation, second = reserve_attempt(operation, task.id, 'primary_repair', task.input_hash, operation.capture.primary,
        owner(3), NOW)
    operation = dispatch_attempt(operation, second, NOW)
    operation = record_return(operation, second, json.dumps({'payload': repair}), 'completed', usage(), cleaned(), returned_at=NOW)
    operation, facts, repaired = parse_proposal(operation, second, captured, [source], facts)
    assert repaired.state == 'provisional', repaired.errors
    value = make_review_input(operation, repaired, captured, [source], operation.capture.primary, effective_cells=[],
        semantic_context={'capturedTaskInput': operation.task_inputs[0].value}, previous=(proposal, first_receipt))
    settled = by_field(value, operation.allocations)
    assert (('a', 'title'), 'reused') not in settled and (('a', 'title'), 'verbatim') not in settled
    assert {(('b', field), 'reused') for field in ['status', 'year']} <= settled
    reused = [check for check in value.settled if check.target_id == failing]
    assert reused and all(check.disposition == 'violation' and check.origin == 'reused' for check in reused)
    assert {target.target_id for target in model_targets(value)} == {operation.allocations[0].cell_ids['title'], 'scope-' + task.id}
    # A clean model answer keeps the reused finding: the category stays rejected without a second look.
    operation, review = reserve_attempt(operation, task.id, 'replacement_review', digest(value), value.policy, owner(4), NOW)
    operation.review_inputs.append(ReviewInputRecord(id='replacement-input', attemptId=review, inputHash=digest(value), value=value))
    operation.attempts[-1].review_input_record_id = 'replacement-input'
    operation = dispatch_attempt(operation, review, NOW)
    operation = record_return(operation, review, json.dumps({'payload': by_reference({'results': []}, value)}), 'completed',
        usage(), cleaned(), returned_at=NOW)
    operation, receipt = record_review(operation, review, [source], NOW)
    decision = decide_review(value, receipt, repaired)
    assert failing not in decision.admitted_cell_ids and operation.allocations[0].cell_ids['title'] in decision.admitted_cell_ids
    assert first_value.settled and all(check.origin == 'verbatim' for check in first_value.settled)


def test_a_category_is_left_to_the_model_even_when_its_word_stands_in_the_cited_line():
    # Parallel review (2026-10-29): «not published» states the word published, not the category published; D115
    # leaves categories with the model.
    from types import SimpleNamespace
    from packages.resume_core.models.contracts import Source
    from packages.resume_core.template_identity import capture_span
    from packages.resume_core.template_review import settled_checks
    from packages.resume_core.templates.compiler import sha256
    text = 'Reliable Queues, Systems Notes, not published'
    src = Source(id='source-category', revision=1, originalName='category.txt', mimeType='text/plain',
        byteSha256=sha256(text.encode()), byteRef='sources/category.txt', parser='text', parserVersion='1',
        units=[{'id': 'unit-category', 'revision': 1, 'order': 0, 'text': text,
            'location': {'kind': 'pasted', 'index': 0, 'row': None, 'column': None}, 'disposition': 'shown',
            'representedFactIds': []}], overlays=[], warnings=[])
    span = capture_span(src, src.units[0])
    keys = ('title', 'journal', 'status')
    payload = [{'title': 'Reliable Queues', 'journal': 'Systems Notes', 'year': None, 'url': None, 'status': 'published'}]
    proposal = SimpleNamespace(reply=SimpleNamespace(payload=payload), resolved_fields=[SimpleNamespace(item_handle='item-a',
        field_key=key, pointer='/0/' + key, evidence=[span]) for key in keys])
    allocations = [SimpleNamespace(item_handle='item-a', cell_ids={key: 'cell-' + key for key in keys})]
    targets = [SimpleNamespace(rule_id='support', target_id='cell-' + key) for key in keys]
    schema = package().blocks[0].full_schema
    settled = settled_checks(proposal, targets, allocations, [src], rewrite_fields=[], content_schema=schema)
    assert {check.target_id for check in settled} == {'cell-title', 'cell-journal'}
    # Without the block's schema the word alone settled the category.
    assert 'cell-status' in {check.target_id for check in settled_checks(proposal, targets, allocations, [src], rewrite_fields=[])}
