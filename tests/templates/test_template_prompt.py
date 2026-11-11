"""The text the model reads of a captured request: compact under the current reply protocols, and exactly as it was
sent for a request stored under an earlier protocol, so an import started before the change resumes with it."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from packages.resume_core.importing.template_import import spent_calls
from packages.resume_core.importing.template_identity import evidence_options
from packages.resume_core.importing.template_prompt import compact, model_prompt
from packages.resume_core.models.contracts import Source
from packages.resume_core.hashing import sha256
from packages.resume_core.sources import capture_span, line_spans
from packages.resume_core.templates.replies import (OUTLINE_PROTOCOL, OUTLINE_REVIEW_PROTOCOL, PROPOSAL_PROTOCOL,
    REVIEW_PROTOCOL)
from tests.templates.pipeline_fixtures import blocks_package
from tests.templates.template_runtime_fixtures import RuntimeFixture, import_task
from tests.templates.test_semantic_admission import raw_proposal
from tests.templates.test_template_pipeline import account_failure

# Requests of every slot as a scripted two-block import stored them before the compact form (4550f82f: proposal and
# review protocol 5, outline protocols 1), each with the prompt that code sent, and the reply protocols of that code.
EARLIER = Path('tests/fixtures/synthetic/templates/earlier-protocol-requests.json')


def earlier():
    return json.loads(EARLIER.read_text())


def source(*texts):
    raw = '\n'.join(texts).encode()
    return Source(id='source-prompt', revision=1, originalName='prompt.txt', mimeType='text/plain', byteSha256=sha256(raw),
        byteRef='sources/prompt.txt', parser='text', parserVersion='1', units=[{'id': 'unit-' + str(index), 'revision': 1,
            'order': index, 'text': text, 'location': {'kind': 'pasted', 'index': index, 'row': None, 'column': None},
            'disposition': 'shown', 'representedFactIds': []} for index, text in enumerate(texts)], overlays=[], warnings=[])


def table(src, spans):
    return [option.model_dump(mode='json', by_alias=True) for option in evidence_options(spans, [src])]


DECLARATION = {'id': 'papers', 'extract': ['One entry per paper line.'], 'content_schema': {'type': 'array'},
    'bindings': [{'pointer': '/*/title', 'semantic_type': 'papers', 'field': 'title', 'relation': None}], 'checks': [],
    'view': {'mode': 'items', 'nodes': []}, 'placement': {'region': 'main', 'order': 1}}
OTHERS = [{'block': 'more-papers', 'title': 'More papers', 'extract': ['Collect every paper again.']}]


def test_requests_stored_under_the_earlier_protocols_read_byte_for_byte_as_they_were_sent():
    stored = earlier()['requests']
    assert {row['label'].split()[0] for row in stored} == {'initial', 'outline', 'outline_review', 'review',
        'primary_repair', 'replacement_review'}
    for row in stored:
        assert not compact(row['request'])
        assert model_prompt(row['request']) == row['prompt'], row['label']


def test_a_compact_request_offers_lines_as_pairs_and_a_whole_unit_by_its_first_and_last_line():
    src = source('Alex Example\nExample Labs, engineer\n\n  \nQueue Systems\n', 'Reliable Queues', 'First line\nSecond line')
    jobs, single, unlined = src.units
    # A unit with its lines, a one-line unit, a unit offered whole alone and a span over two lines (a cell's evidence).
    spans = [capture_span(src, jobs), *line_spans(src, jobs), capture_span(src, single), capture_span(src, unlined),
        capture_span(src, jobs, 0, 36)]
    value = {'protocol': 'template_import_v1', 'replyProtocol': PROPOSAL_PROTOCOL, 'evidence': table(src, spans),
        'declaration': {'id': 'papers'}}
    before = deepcopy(value)
    prompt = model_prompt(value)
    assert prompt.startswith('{"protocol":"template_import_v1","evidence":[["S1",["S2","S4"]],["S2","Alex Example\\n"]')
    assert json.loads(prompt)['evidence'] == [['S1', ['S2', 'S4']], ['S2', 'Alex Example\n'],
        ['S3', 'Example Labs, engineer\n'], ['S4', 'Queue Systems\n'], ['S5', 'Reliable Queues'],
        ['S6', 'First line\nSecond line'], ['S7', 'Alex Example\nExample Labs, engineer\n']]
    assert value == before
    # The same request stored under protocol 5 offers every entry with its text, as it was sent.
    stored = {**value, 'replyProtocol': earlier()['protocols']['proposal']}
    assert json.loads(model_prompt(stored))['evidence'] == [{'ref': option['ref'], 'text': option['text']}
        for option in value['evidence']]


def test_a_compact_request_leaves_the_document_out_of_its_declaration_and_names_other_blocks_by_title():
    extraction = {'protocol': 'template_import_v1', 'replyProtocol': PROPOSAL_PROTOCOL, 'evidence': [],
        'declaration': DECLARATION, 'modelInstructions': {'extract': ['Keep facts.']}}
    outline = {**extraction, 'slot': 'outline', 'replyProtocol': OUTLINE_PROTOCOL}
    outline_review = {**extraction, 'slot': 'outline_review', 'replyProtocol': OUTLINE_REVIEW_PROTOCOL,
        'otherBlocks': OTHERS, 'outline': {'entries': []}}
    review = {'protocol': 'template_import_v1', 'evidence': [], 'targets': [], 'semanticContext': {
        'replyProtocol': REVIEW_PROTOCOL, 'otherBlocks': OTHERS, 'checks': [], 'taskInput': {'declaration': DECLARATION,
            'modelInstructions': {'extract': ['Keep facts.']}, 'replyProtocol': PROPOSAL_PROTOCOL}}}
    values = [extraction, outline, outline_review, review]
    before = deepcopy(values)
    sent = [json.loads(model_prompt(value)) for value in values]
    assert values == before
    kept = {key: value for key, value in DECLARATION.items() if key not in {'view', 'placement'}}
    assert sent[0]['declaration'] == sent[1]['declaration'] == sent[2]['declaration'] == kept
    assert sent[2]['otherBlocks'] == [{'block': 'more-papers', 'title': 'More papers'}]
    # A review keeps the content schema, extract rules and checks of its task and the model instructions.
    task = sent[3]['semanticContext']['taskInput']
    assert task == {'declaration': {key: value for key, value in kept.items() if key != 'bindings'},
        'modelInstructions': {'extract': ['Keep facts.']}}
    assert sent[3]['semanticContext']['otherBlocks'] == [{'block': 'more-papers', 'title': 'More papers'}]
    assert model_prompt(review).startswith('{"protocol":"template_import_v1","evidence":[],')
    # Stored under the earlier protocols, the same requests keep the whole declaration and the other blocks' rules.
    protocols = earlier()['protocols']
    stored = [{**extraction, 'replyProtocol': protocols['proposal']}, {**outline, 'replyProtocol': protocols['outline']},
        {**outline_review, 'replyProtocol': protocols['outlineReview']},
        {**review, 'semanticContext': {**review['semanticContext'], 'replyProtocol': protocols['review']}}]
    sent = [json.loads(model_prompt(value)) for value in stored]
    assert all(value['declaration'] == DECLARATION for value in sent[:3]) and sent[2]['otherBlocks'] == OTHERS
    assert sent[3]['semanticContext']['taskInput']['declaration'] == DECLARATION
    assert sent[3]['semanticContext']['otherBlocks'] == OTHERS


@pytest.mark.asyncio
async def test_a_reply_that_cites_a_whole_unit_by_its_ref_still_resolves_to_the_unit(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and [task.state for task in result.tasks] == ['accepted']
    unit = fixture.source.units[0]
    last = 'S' + str(1 + len(line_spans(fixture.source, unit)))
    # The extraction and its review read the unit by its first and last line; the scripted reply cites the unit.
    assert [json.loads(prompt)['evidence'][0] for prompt in fixture.transport.prompts] == [['S1', ['S2', last]]] * 2
    reply = json.loads(result.attempts[0].raw_return)['payload']
    assert {ref for field in reply['fields'] for ref in field['evidence']} == {'S1'}
    assert all(field.evidence == [capture_span(fixture.source, unit)] for field in result.proposals[0].resolved_fields)


def earlier_protocols(patched):
    """The reply protocols of the code before the compact form, as its requests carry them."""
    from packages.resume_core.importing import template_review
    from packages.resume_core.templates import replies
    from resume_api.importer import template_pipeline
    protocols = earlier()['protocols']
    patched.setattr(replies, 'PROPOSAL_PROTOCOL', protocols['proposal'])
    patched.setattr(replies, 'CONTENT_ONLY_RULES', protocols['contentOnlyRules'])
    patched.setattr(template_pipeline, 'PROPOSAL_PROTOCOL', protocols['proposal'])
    patched.setattr(template_pipeline, 'OUTLINE_PROTOCOL', protocols['outline'])
    patched.setattr(template_pipeline, 'OUTLINE_REVIEW_PROTOCOL', protocols['outlineReview'])
    patched.setattr(template_review, 'REVIEW_PROTOCOL', protocols['review'])


@pytest.mark.asyncio
async def test_an_import_stopped_under_the_earlier_protocols_resumes_and_publishes_with_the_text_it_started(tmp_path,
        monkeypatch):
    fixture = RuntimeFixture(tmp_path, captured=blocks_package(2), cap=20, fallback=False)
    def script(_request, value):
        if 'targets' in value:
            account_failure('QUOTA_EXHAUSTED')
        return raw_proposal(fixture.source)
    fixture.transport.scripted = script
    with monkeypatch.context() as patched:
        earlier_protocols(patched)
        status = await import_task(fixture)
    assert (status['state'], status['error']) == ('failed', 'QUOTA_EXHAUSTED')
    stopped = fixture.current().pre_draft.template_operations[0]
    fixture.transport.scripted = None
    resumed = await import_task(fixture, kind='resume', operation_id=stopped.id)
    assert (resumed['state'], resumed['error']) == ('succeeded', None)
    published = fixture.current().project.template_operations[0]
    assert [task.state for task in published.tasks] == ['accepted', 'accepted'] and not published.issues
    assert {result.disposition for result in published.task_results} == {'admitted'}
    # The first block's extraction, its stopped review and that review run again, then the second block's two calls.
    prompts, calls = fixture.transport.prompts, fixture.transport.calls
    assert spent_calls(published) == len(prompts) == 5
    assert all(model_prompt(value) == prompt for value, prompt in zip(calls, prompts, strict=True))
    # The stored review of protocol 5 is sent again as it was, and its reply lists failing checks only.
    assert prompts[2] == prompts[1] and calls[2]['semanticContext']['replyProtocol']['version'] == 'template-review-protocol-5'
    assert all(set(json.loads(prompt)['evidence'][0]) == {'ref', 'text'} for prompt in prompts[:3])
    lines = len(line_spans(fixture.source, fixture.source.units[0]))
    assert [json.loads(prompt)['evidence'][0] for prompt in prompts[3:]] == [['S1', ['S2', 'S' + str(1 + lines)]]] * 2
