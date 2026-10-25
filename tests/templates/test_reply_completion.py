"""S7d protocol 5: the coordinator derives the bookkeeping a reply's payload implies (synthetic F10 text only)."""

from copy import deepcopy
import json

import pytest

from packages.resume_core.template_completion import complete_reply
from packages.resume_core.template_identity import capture_span, evidence_options, line_spans, offered_evidence, source_slice
from packages.resume_core.template_import import admit_operation, capture_task_input, dispatch_attempt, record_return, reserve_attempt
from packages.resume_core.templates.projection import pointer_tokens
from tests.templates.evidence_references import by_reference
from tests.templates.generic_fixtures import TABLES, block_reply, date, generic_package, job, period
from tests.templates.pipeline_fixtures import NOW, cleaned, owner, setup_operation, usage
from tests.templates.storage_fixtures import source_fixture


def request_for(src):
    """The whole unit and each of its lines, offered by reference as the coordinator offers them."""
    unit = src.units[0]
    options = evidence_options([capture_span(src, unit), *line_spans(src, unit)], [src])
    return {'protocol': 'template_import_v1', 'evidence': [option.model_dump(mode='json', by_alias=True) for option in options],
        'references': {'items': [], 'cells': [], 'relations': []}}


def refs(request):
    return {option['text'].rstrip('\n'): option['ref'] for option in request['evidence']}


def parsed(block_id, reply_for):
    """Parse the referenced reply reply_for(request) returns for one Generic block of the F10 source."""
    package = generic_package()
    src, _raw = source_fixture('F10')
    operation, _command, _package, _src, facts = setup_operation(captured=package, src=src, cap=4)
    operation = admit_operation(operation, NOW)
    task = next(task for task in operation.tasks if task.block_id == block_id)
    # Earlier blocks are not run here; the block's own reply is what is under test.
    task.dependencies = []
    request = request_for(src)
    operation = capture_task_input(operation, task.id, request, [], NOW)
    task = next(value for value in operation.tasks if value.id == task.id)
    operation, attempt = reserve_attempt(operation, task.id, 'initial', task.input_hash, operation.capture.primary, owner(1), NOW,
        request_value=request)
    operation = dispatch_attempt(operation, attempt, NOW)
    operation = record_return(operation, attempt, json.dumps({'payload': reply_for(request)}), 'completed', usage(), cleaned(),
        returned_at=NOW)
    operation, _facts, proposal = parse_proposal_of(operation, attempt, package, src, facts)
    return proposal, operation, src


def parse_proposal_of(operation, attempt, package, src, facts):
    from packages.resume_core.template_proposals import parse_proposal
    return parse_proposal(operation, attempt, package, [src], facts)


def reply(payload, fields=(), **parts):
    return {'schemaVersion': 3, 'payload': payload, 'discoveries': parts.get('discoveries'), 'fields': list(fields),
        'lineage': parts.get('lineage'), 'relations': parts.get('relations')}


def entry(pointer, evidence, key=None, item=None):
    return {'item': item, 'fieldKey': key, 'pointer': pointer, 'evidence': evidence, 'effectiveCells': None}


def own(key):
    return {'kind': 'discovery_key', 'key': key}


def per_field_identity(request):
    # LIVE-02 identity and location: one discovery per field, each at the field pointer instead of the item root.
    ref = refs(request)
    return reply({'name': 'Alex Example', 'profession': 'Backend engineer', 'role_family': {'family': 'other'}},
        [entry('/name', [ref['Alex Example']], 'name', own('person')), entry('/profession', [ref['Backend engineer']], 'profession',
            own('profession')), entry('/role_family/family', [ref['Backend engineer']], 'family', own('family'))],
        discoveries=[{'key': 'person', 'semanticType': 'foldcv:identity', 'pointer': '/name'},
            {'key': 'profession', 'semanticType': 'foldcv:identity', 'pointer': '/profession'},
            {'key': 'family', 'semanticType': 'foldcv:role_family', 'pointer': '/role_family/family'}],
        lineage=[{'kind': 'add', 'parents': [], 'children': ['person', 'profession', 'family']}], relations=[])


def per_field_location(request):
    ref = refs(request)['Location: Example City, Example Country, UTC+1']
    values = {'city': 'Example City', 'country': 'Example Country', 'timezone': 'UTC+1'}
    return reply(values, [entry('/' + key, [ref], key, own('loc-' + key)) for key in values],
        discoveries=[{'key': 'loc-' + key, 'semanticType': 'foldcv:location', 'pointer': '/' + key} for key in values],
        lineage=[{'kind': 'add', 'parents': [], 'children': ['loc-' + key for key in values]}], relations=[])


def verbatim_jobs():
    return [job('Old Systems', 'engineer', period('2010–2012', date('2010', 2010), date('2012', 2012), False), technologies=['Perl']),
        job('Example Labs', 'backend engineer', period('03.2020–11.2023', date('03.2020', 2020, 3), date('11.2023', 2023, 11), False),
            project={'name': 'Queue Platform', 'description': 'message queue platform for internal services.'},
            technologies=['Python', 'PostgreSQL', 'Docker'], tasks=['Implemented queue processing.'],
            results=['Reduced median latency by 80%.'])]


def payload_only(_request):
    # LIVE-02 projects: the payload and nothing else.
    return reply(verbatim_jobs())


def partial_terms(request):
    # LIVE-02 programming: entries for the first values only (50 of 61 there).
    ref = refs(request)['Python, PostgreSQL, Docker']
    return reply({'items': ['Python', 'PostgreSQL', 'Docker', 'Perl']},
        [entry('/items/0', [ref], 'display', own('t0')), entry('/items/1', [ref], 'display', own('t1'))],
        discoveries=[{'key': 't0', 'semanticType': 'foldcv:programming', 'pointer': '/items/0'},
            {'key': 't1', 'semanticType': 'foldcv:programming', 'pointer': '/items/1'}],
        lineage=[{'kind': 'add', 'parents': [], 'children': ['t0', 't1']}], relations=[])


def empty_with_lineage(_request):
    # LIVE-02 opensource: nothing found, but an add lineage without children.
    return reply([], lineage=[{'kind': 'add', 'parents': [], 'children': []}], discoveries=[], relations=[])


def list_entry(request):
    # LIVE-02 data_and_tools: one discovery and one entry for the whole list.
    ref = refs(request)['Python, PostgreSQL, Docker']
    return reply({'items': ['PostgreSQL', 'Docker']}, [entry('/items', [ref], 'display', own('tools'))],
        discoveries=[{'key': 'tools', 'semanticType': 'foldcv:data_and_tools', 'pointer': '/items'}],
        lineage=[{'kind': 'add', 'parents': [], 'children': ['tools']}], relations=[])


def invented_handle(request):
    # LIVE-02 summary: a handle ref the request never offered.
    ref = refs(request)['Summary: Backend engineer focused on reliable queue systems.']
    return reply({'text': 'Backend engineer focused on reliable queue systems.'},
        [entry('/text', [ref], 'text', {'kind': 'handle', 'ref': 'H1'})], discoveries=[], lineage=[], relations=[])


@pytest.mark.parametrize('block_id, reply_for', [('identity', per_field_identity), ('location', per_field_location)])
def test_values_follow_their_pointer_to_their_item_whatever_discoveries_a_reply_names(block_id, reply_for):
    proposal, operation, _src = parsed(block_id, reply_for)
    assert proposal.state == 'provisional', proposal.errors
    items = {field.item_handle for field in proposal.resolved_fields}
    types = sorted(allocation.semantic_type for allocation in operation.allocations)
    assert types == (['foldcv:identity', 'foldcv:role_family'] if block_id == 'identity' else ['foldcv:location'])
    assert len(items) == len(types) and [value.kind for value in proposal.lineage] == ['add']


def test_a_payload_without_bookkeeping_cites_word_for_word_values_and_derives_items_and_relations():
    proposal, operation, src = parsed('projects', payload_only)
    assert proposal.state == 'provisional', proposal.errors
    stated = {field.pointer: [source_slice([src], span) for span in field.evidence] for field in proposal.resolved_fields}
    assert all('Perl' in text for text in stated['/0/technologies/0/display'])
    assert stated['/1/tasks/0/value'] == ['Implemented queue processing.\n']
    assert all('03.2020' in text for text in stated['/1/period/start'])
    # Every project, technology, task and result is owned by its job.
    pointers = {value.key: value.pointer for value in proposal.reply.discoveries}
    jobs = {value.record_id: pointers[value.key] for value in operation.allocations if value.semantic_type == 'foldcv:projects'}
    owned = {pointers[value.key]: value.record_id for value in operation.allocations if value.semantic_type != 'foldcv:projects'}
    relations = {relation.subject_id: relation.target_id for relation in proposal.resolved_relations}
    kinds = sorted(relation.kind for relation in proposal.resolved_relations)
    assert kinds == ['extension_of'] + ['owned_by'] * 6
    assert sorted(jobs.values()) == ['/0', '/1'] and len(owned) == 7 and set(relations) == set(owned.values())
    assert all(jobs[relations[record]] == '/' + pointer_tokens(pointer)[0] for pointer, record in owned.items())


@pytest.mark.parametrize('block_id, reply_for, values', [('programming', partial_terms, 4), ('opensource', empty_with_lineage, 0),
    ('data_and_tools', list_entry, 2)])
def test_missing_list_entries_empty_lineage_and_list_level_evidence_are_completed(block_id, reply_for, values):
    proposal, _operation, src = parsed(block_id, reply_for)
    assert proposal.state == 'provisional', proposal.errors
    assert len(proposal.resolved_fields) == values
    assert all(field.evidence and all(source_slice([src], span).strip() for span in field.evidence) for field in proposal.resolved_fields)


def test_an_unoffered_handle_and_an_unstated_value_are_still_refused_with_the_binding_named():
    proposal, _operation, _src = parsed('summary', invented_handle)
    assert proposal.state == 'invalid' and proposal.errors == ['/payload/fields/0/item: matches none of the allowed shapes']
    unstated = lambda _request: reply({'items': ['Python', 'Rust']})
    proposal, _operation, _src = parsed('programming', unstated)
    assert proposal.state == 'invalid' and proposal.errors[0].endswith('missing /items/1 (display)')


def test_a_complete_protocol_4_reply_is_left_as_it_is():
    # P11: completion adds nothing to an explicit reply, so earlier replies keep their proposal hash.
    package = generic_package()
    blocks = {block.id: block for block in package.definition.blocks}
    src, _raw = source_fixture('F10')
    request = request_for(src)
    table = offered_evidence(request)
    for block_id in ['identity', 'projects', 'programming', 'location']:
        payload, cites = TABLES['F10'](True)[block_id]
        explicit = by_reference(block_reply(blocks[block_id], payload, src, cites), request)
        explicit['schemaVersion'] = 3
        assert complete_reply(deepcopy(explicit), blocks[block_id].bindings, table, None) == explicit, block_id


def test_derived_items_and_relations_match_an_explicit_reply():
    # P11: the payload alone yields the same values, items and ownership as the scripted explicit reply.
    explicit, _operation, _src = parsed('projects', lambda request: {**by_reference(block_reply(
        {block.id: block for block in generic_package().definition.blocks}['projects'], verbatim_jobs(),
        source_fixture('F10')[0]), request), 'schemaVersion': 3})
    derived, _operation, _src = parsed('projects', payload_only)
    assert explicit.state == derived.state == 'provisional', (explicit.errors, derived.errors)
    def shape(proposal):
        return (sorted((field.pointer, field.field_key) for field in proposal.resolved_fields),
            sorted(relation.kind for relation in proposal.resolved_relations), len({field.item_handle for field in proposal.resolved_fields}))
    assert shape(explicit) == shape(derived)


@pytest.mark.asyncio
async def test_an_generic_import_with_lean_first_replies_publishes_the_same_blocks(tmp_path):
    # P13: first replies carry the payload and entries only for values not copied word for word; no discoveries,
    # lineage or relations. Repairs stay explicit. The published blocks match the explicit F10 import.
    import re
    from packages.resume_core.template_completion import stated_text
    from tests.templates.generic_fixtures import F10_REJECTED, F10_RESULT, generic_import
    from tests.templates.test_generic_import import views
    src = source_fixture('F10')[0]
    text, blocks = src.units[0].text, {block.id: block for block in generic_package().definition.blocks}
    def lean(script):
        def scripted(request, value):
            if 'targets' not in value and value.get('slot') != 'initial':
                # A repair selects the items the lean first reply allocated, named as the scripted reply names them.
                block = blocks[value['declaration']['id']]
                payload, cites = TABLES['F10'](True)[block.id]
                named = {(item['semanticType'], item['pointer']): item['key']
                    for item in block_reply(block, payload, src, cites)['discoveries']}
                def scripted_key(key):
                    pointer, semantic = key.removeprefix('auto').rsplit('@', 1)
                    return named.get((semantic, pointer), key)
                value = {**value, 'capturedHandles': [{**handle, 'key': scripted_key(handle['key'])}
                    for handle in value['capturedHandles']]}
            answer = script(request, value)
            if 'targets' in value or value.get('slot') != 'initial':
                return answer
            def copied(field):
                stated = stated_text(answer['payload'], field['pointer'])
                return stated is not None and re.search(r'(?<!\w)' + re.escape(stated) + r'(?!\w)', text) is not None
            return {**answer, 'discoveries': [], 'lineage': [], 'relations': [],
                'fields': [field for field in answer['fields'] if not copied(field)]}
        return scripted
    _fixture, result, workspace, _originals = await generic_import(tmp_path, 'F10', wrap=lean)
    assert result.state == 'published' and result.publication.state == 'saved'
    shown = views(workspace)
    assert shown['location'] == ['ЛОКАЦИЯ', 'Example City, Example Country, UTC+1']
    assert shown['opensource'] == ['OPEN SOURCE', 'Queue Tools'] and shown['programming'] == ['ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ', 'Python, Perl']
    projects = shown['projects']
    assert projects.count('Implemented queue processing.') == 1 and projects[-1] == F10_RESULT
    assert F10_REJECTED not in '\n'.join(value for values in shown.values() for value in values)
    fallback = [issue for issue in workspace.project.import_issues if issue.code == 'IMPORT_SOURCE_FALLBACK']
    assert [(issue.category, issue.rule_id) for issue in fallback] == [('content_violation', 'projects-support')]
