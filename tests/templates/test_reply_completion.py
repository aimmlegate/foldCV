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


def test_an_unoffered_handle_is_dropped_without_offers_and_an_unstated_value_is_still_refused_with_the_binding_named():
    # I3 (LIVE-12): a request that offers no items cannot mean a handle; the selection is dropped and the item derived.
    proposal, _operation, _src = parsed('summary', invented_handle)
    assert proposal.state == 'provisional', proposal.errors
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


@pytest.mark.slow
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


def test_a_value_whose_words_one_line_states_in_another_order_cites_that_line():
    # LIVE-05: a repair joined listed tools into one value; its words are stated, though not word for word.
    proposal, _operation, src = parsed('programming', lambda _request: reply({'items': ['docker Python']}))
    assert proposal.state == 'provisional', proposal.errors
    [field] = proposal.resolved_fields
    assert [source_slice([src], span).strip() for span in field.evidence] == ['Python, PostgreSQL, Docker']
    proposal, _operation, _src = parsed('programming', lambda _request: reply({'items': ['Docker and Rust']}))
    assert proposal.state == 'invalid' and proposal.errors[0].endswith('missing /items/0 (display)')


def test_an_entry_past_the_payload_is_dropped_and_a_wrong_type_item_ref_becomes_a_new_item():
    # LIVE-05 repairs: entries for /items/25 and /items/26 of a 25-item list; a skill named by the role family's ref.
    from packages.resume_core.models.template_import import ReferenceTable
    blocks = {block.id: block for block in generic_package().definition.blocks}
    src, _raw = source_fixture('F10')
    request = request_for(src)
    request['references']['items'] = [{'ref': 'H1', 'itemHandle': 'item-role', 'semanticType': 'foldcv:role_family', 'key': 'family'}]
    line = refs(request)['Python, PostgreSQL, Docker']
    given = reply({'items': ['Python']}, [entry('/items/0', [line], 'display', {'kind': 'handle', 'ref': 'H1'}),
        entry('/items/1', [line], 'display', {'kind': 'handle', 'ref': 'H1'})])
    completed = complete_reply(given, blocks['programming'].bindings, offered_evidence(request),
        ReferenceTable.model_validate(request['references']))
    [field] = completed['fields']
    [discovery] = completed['discoveries']
    assert field['pointer'] == '/items/0' and field['evidence'] == [line]
    assert field['item'] == {'kind': 'discovery_key', 'key': discovery['key']} and discovery['pointer'] == '/items/0'
    unoffered = reply({'items': ['Python']}, [entry('/items/0', [line], 'display', {'kind': 'handle', 'ref': 'H9'})])
    kept = complete_reply(unoffered, blocks['programming'].bindings, offered_evidence(request),
        ReferenceTable.model_validate(request['references']))
    assert kept['fields'][0]['item'] == {'kind': 'handle', 'ref': 'H9'}


def test_an_entry_for_the_raw_wording_of_a_period_cites_the_values_read_from_it():
    # LIVE-06: a projects reply cited /0/period/raw, which no binding holds; start, end and ongoing are read from it.
    def raw_period(request):
        block = {value.id: value for value in generic_package().definition.blocks}['projects']
        explicit = {**by_reference(block_reply(block, verbatim_jobs(), source_fixture('F10')[0]), request), 'schemaVersion': 3}
        period = [field for field in explicit['fields'] if field['pointer'].startswith('/0/period/')]
        explicit['fields'] = [field for field in explicit['fields'] if field not in period] + [
            entry('/0/period/raw', period[0]['evidence'])]
        return explicit
    proposal, _operation, _src = parsed('projects', raw_period)
    assert proposal.state == 'provisional', proposal.errors
    explicit, _operation, _src = parsed('projects', lambda request: {**by_reference(block_reply(
        {value.id: value for value in generic_package().definition.blocks}['projects'], verbatim_jobs(),
        source_fixture('F10')[0]), request), 'schemaVersion': 3})
    def period(value):
        return sorted((field.pointer, tuple((span.start, span.end) for span in field.evidence))
            for field in value.resolved_fields if field.pointer.startswith('/0/period/'))
    assert [pointer for pointer, _spans in period(proposal)] == ['/0/period/end', '/0/period/ongoing', '/0/period/start']
    assert period(proposal) == period(explicit)


def test_an_entry_inside_a_bound_value_cites_that_value():
    def inner(request):
        block = {value.id: value for value in generic_package().definition.blocks}['projects']
        explicit = {**by_reference(block_reply(block, verbatim_jobs(), source_fixture('F10')[0]), request), 'schemaVersion': 3}
        for field in explicit['fields']:
            if field['pointer'] == '/0/period/start':
                field['pointer'], field['fieldKey'], field['item'] = '/0/period/start/raw', None, None
        return explicit
    proposal, _operation, _src = parsed('projects', inner)
    assert proposal.state == 'provisional', proposal.errors
    [start] = [field for field in proposal.resolved_fields if field.pointer == '/0/period/start']
    assert start.field_key == 'start' and start.evidence


def test_an_entry_no_binding_holds_is_dropped_and_a_foreign_field_name_joins_the_value_entry():
    # LIVE-07 repairs: an entry at /0/project of a job without a project, and a tool cited again under the role
    # family's field name and item ref next to its own entry.
    from packages.resume_core.models.template_import import ReferenceTable
    blocks = {block.id: block for block in generic_package().definition.blocks}
    src, _raw = source_fixture('F10')
    request = request_for(src)
    request['references']['items'] = [{'ref': 'H1', 'itemHandle': 'item-role', 'semanticType': 'foldcv:role_family', 'key': 'family'}]
    line = refs(request)['Python, PostgreSQL, Docker']
    given = reply({'items': ['Python']}, [entry('/items/0', [line], 'family', {'kind': 'handle', 'ref': 'H1'}),
        entry('/items/0', [line], 'display')])
    completed = complete_reply(given, blocks['programming'].bindings, offered_evidence(request),
        ReferenceTable.model_validate(request['references']))
    [field] = completed['fields']
    assert (field['pointer'], field['fieldKey'], field['evidence']) == ('/items/0', 'display', [line])
    def null_project(request):
        explicit = {**by_reference(block_reply(blocks['projects'], verbatim_jobs(), source_fixture('F10')[0]), request),
            'schemaVersion': 3}
        explicit['fields'].append(entry('/0/project', explicit['fields'][0]['evidence']))
        return explicit
    proposal, _operation, _src = parsed('projects', null_project)
    assert proposal.state == 'provisional', proposal.errors
    assert not any(field.pointer == '/0/project' for field in proposal.resolved_fields)


def test_an_undeclared_relation_is_dropped_and_a_captured_relation_named_for_another_subject_becomes_new():
    # LIVE-11 repair: one job "owned by" another, and a captured relation ref reused for a different item.
    from packages.resume_core.models.template_import import ReferenceTable
    blocks = {block.id: block for block in generic_package().definition.blocks}
    package = generic_package()
    allowed = {(declaration.id, relation.kind, target) for declaration in package.definition.fact_types
        for relation in declaration.relations for target in relation.target_types}
    src = source_fixture('F10')[0]
    def bad_relations(request):
        explicit = {**by_reference(block_reply(blocks['projects'], verbatim_jobs(), src), request), 'schemaVersion': 3}
        jobs = [value['key'] for value in explicit['discoveries'] if value['semanticType'] == 'foldcv:projects']
        evidence = explicit['fields'][0]['evidence']
        explicit['relations'].append({'relation': {'kind': 'new', 'key': 'job-in-job'}, 'kind': 'owned_by',
            'subject': {'kind': 'discovery_key', 'key': jobs[1]}, 'target': {'kind': 'discovery_key', 'key': jobs[0]},
            'evidence': evidence})
        return explicit
    proposal, _operation, _src = parsed('projects', bad_relations)
    assert proposal.state == 'provisional', proposal.errors
    assert not any(relation.kind == 'owned_by' and relation.subject_id == relation.target_id for relation in proposal.resolved_relations)
    request = request_for(src)
    request['references'] = {'items': [{'ref': 'H1', 'itemHandle': 'item-job', 'semanticType': 'foldcv:projects', 'key': 'job'}],
        'cells': [], 'relations': [{'ref': 'R1', 'relationId': 'relation-old', 'kind': 'owned_by', 'subject': 'H9', 'target': 'H1'}]}
    explicit = by_reference(block_reply(blocks['projects'], verbatim_jobs()[:1], src), request_for(src))
    technology = next(value['key'] for value in explicit['discoveries'] if value['semanticType'] == 'foldcv:project_technology')
    job = next(value['key'] for value in explicit['discoveries'] if value['semanticType'] == 'foldcv:projects')
    explicit['relations'] = [{'relation': {'kind': 'relation', 'ref': 'R1'}, 'kind': 'owned_by',
        'subject': {'kind': 'discovery_key', 'key': technology}, 'target': {'kind': 'discovery_key', 'key': job},
        'evidence': explicit['fields'][0]['evidence']}]
    completed = complete_reply(explicit, blocks['projects'].bindings, offered_evidence(request),
        ReferenceTable.model_validate(request['references']), allowed)
    reused = [value for value in completed['relations'] if value['subject'] == {'kind': 'discovery_key', 'key': technology}]
    assert reused and all(value['relation']['kind'] == 'new' for value in reused)


# I2 (2026-10-25): a reworded value binds to the lines of its own item that state its word stems.
from types import SimpleNamespace

from packages.resume_core.template_completion import stating_stems


def stem_table(*lines):
    """Offered lines in source order, one unit each; only text and span identity matter to the matcher."""
    return {'S%d' % (index + 1): SimpleNamespace(ref='S%d' % (index + 1), text=text,
        span=SimpleNamespace(source_id='src', source_revision=1, unit_id='src/unit_%d' % index, unit_revision=1, start=0, end=len(text)))
        for index, text in enumerate(lines)}


def table_texts(table):
    return [option.text for option in table.values()]


def test_a_reworded_value_binds_to_the_lines_that_state_its_stems():
    # LIVE-12: the template asks for verbs, the CV has nouns; a line split in two states one bullet.
    table = stem_table('Ак Барс Цифровые Технологии', '- Создание и развитие микросервисов, осуществляющие интеграцию вендорских',
        'платформ в информационной системе Гарантия.', '- Разработка генерации Microsoft Excel и Word файлов.')
    assert stating_stems('Создавал и развивал микросервисы для интеграции вендорских платформ в информационную систему «Гарантия».',
        table) == ['S2', 'S3']
    assert stating_stems('Разрабатывал генерацию файлов Microsoft Excel и Word.', table) == ['S4']


def test_short_words_and_a_typo_do_not_decide_a_binding():
    # 'для', 'код', 'гос.' and a misspelt source word neither pull in a line nor block one near the item's own lines.
    table = stem_table('Ак Барс Цифровые Технологии', '- Переработка старого кода, ревесринжериинг старого и вендорского функционала с',
        'восстановлением описания.', *['строка %d' % index for index in range(20)], 'Государственная морская академия')
    assert stating_stems('Перерабатывал старый код, проводил реверс-инжиниринг старого и вендорского функционала и восстанавливал его описание.',
        table, anchors=['S1']) == ['S2', 'S3']
    assert stating_stems('Нанимал кандидатов.', stem_table('Компания', '- Найм кандидатов.'), anchors=['S1']) == ['S2']


def test_the_item_window_keeps_a_value_on_its_own_lines():
    # LIVE-12: 'Разрабатывал генерацию PDF-файлов' belongs to the fourth job, not to the first job's Excel line, and a claim
    # the item's lines do not state stays unbound even when another company's description states it.
    table = stem_table('ROKO Labs разрабатывал IT продукты для различных заказчиков из США.', '- Разработка генерации Microsoft Excel и Word файлов.',
        *['строка %d' % index for index in range(10)], 'ООО Перфект', 'Компания Перфект создавала IT продукты для бирж.',
        '- Разработка сайта на ASP.NET Web Page.', '- Разработка генерации PDF файлов.')
    assert stating_stems('Разрабатывал генерацию PDF-файлов.', table, anchors=['S13', 'S14']) == ['S16']
    assert stating_stems('Проводил собеседования.', stem_table('- Проведение собеседований.', *table_texts(table)), anchors=['S14', 'S15']) == []
    # A short value is one source line: two common stems on two different lines are no statement of it.
    assert stating_stems('Разрабатывал продукт.', table, anchors=['S13', 'S14']) == ['S14']
    # Without anchors the whole source is searched and the first line chosen opens the window for the rest.
    assert stating_stems('Разрабатывал генерацию PDF-файлов.', table) == ['S16']


def test_the_previous_items_last_line_loses_to_the_items_own_line():
    # Review 2026-10-26: the line just above the anchors ends the previous job; stating more stems must not win it.
    table = stem_table('ООО Альфа', '- Разработка генерации PDF-файлов для внутренних отчётов.', 'ООО Перфект',
        'Компания Перфект создавала IT продукты.', '- Разработка генерации PDF файлов.')
    assert stating_stems('Разрабатывал генерацию PDF-файлов для внутренних отчётов.', table, anchors=['S3', 'S4']) == ['S5']
    table = stem_table('- Разработка генерации Microsoft Excel и Word файлов.', 'ООО Перфект',
        'Компания Перфект создавала IT продукты.', '- Разработка генерации Excel отчётов.')
    assert stating_stems('Разрабатывал генерацию файлов Microsoft Excel и Word.', table, anchors=['S2', 'S3']) == ['S4']


def test_an_inferred_sentence_in_another_language_stays_unbound():
    # LIVE-09: the model translated and inferred; two shared numbers are no statement of the value.
    table = stem_table('Backend (Golang, NodeJS, PHP, C)', 'Июль 2021 — март 2025 (3 года 9 месяцев)', 'Основной стек: Go')
    assert stating_stems('Worked in a Golang team for about 4 years (July 2021–March 2025; 3 years 9 months).', table) == []
    assert stating_stems('WCF', table) == []


def test_a_merged_technology_list_cites_its_employer_and_technology_lines():
    table = stem_table('ООО Перфект', 'Компания Перфект создавала IT продукты для работы с финансовыми биржами.', 'Разработчик',
        'ТЕХНОЛОГИИ: Microsoft .NET Framework 3.5, ADO.NET, WCF, WPF, WinFroms, SQL Server', '2008 R2, MS Report Service, Quik, Plaza2.')
    refs = stating_stems('ООО Перфект — Microsoft .NET Framework 3.5, ADO.NET, WCF, WPF, WinFroms, SQL Server 2008 R2, MS Report Service, Quik, Plaza2.', table)
    assert set(refs) == {'S4', 'S5', 'S2'} or set(refs) == {'S4', 'S5', 'S1'}


# I3 (2026-10-25): a request that offers no items or relations asks for payload and fields only.
from packages.resume_core.models.template_import import ReferenceTable
from packages.resume_core.templates.replies import PROPOSAL_PROTOCOL, proposal_protocol, proposal_schema, strip_unoffered_bookkeeping


def test_a_request_without_offers_has_no_bookkeeping_keys_and_ignores_the_ones_a_reply_still_sends():
    # LIVE-12: the first projects reply named a relation target nobody offered and the schema refused the whole reply.
    def with_bookkeeping(request):
        value = payload_only(request)
        value['discoveries'] = [{'key': 'proj', 'semanticType': 'foldcv:project', 'pointer': '/0/project'}]
        value['lineage'] = [{'kind': 'add', 'parents': [], 'children': ['proj']}]
        value['relations'] = [{'relation': {'kind': 'new', 'key': 'owned'}, 'kind': 'owned_by', 'subject': {'kind': 'discovery_key', 'key': 'proj'},
            'target': {'kind': 'handle', 'ref': 'item-/0'}, 'evidence': [request['evidence'][0]['ref']]}]
        return value
    proposal, _operation, _src = parsed('projects', with_bookkeeping)
    assert proposal.state == 'provisional', proposal.errors
    assert [value.kind for value in proposal.lineage] == ['add'] and proposal.resolved_relations
    full = next(block.full_schema for block in generic_package().blocks if block.id == 'projects')
    nothing = ReferenceTable.model_validate({'items': [], 'cells': [], 'relations': []})
    schema = proposal_schema(full, ['S1'], nothing)
    assert schema['$defs']['ItemRef'] == {'type': 'string'} and schema['$defs']['RelationRef'] == {'type': 'string'}
    assert proposal_schema(full, ['S1'], None)['$defs']['ItemRef'] == {'type': 'string', 'not': {}}
    assert proposal_protocol(None) is PROPOSAL_PROTOCOL and 'send null' not in proposal_protocol(nothing)['rules'][0]
    assert 'no lineage or relations' in proposal_protocol(nothing)['rules'][3]
    handle = {'kind': 'handle', 'ref': 'item-/0'}
    keyed = {'kind': 'discovery_key', 'key': 'proj'}
    stripped = strip_unoffered_bookkeeping({'payload': [], 'discoveries': [],
        'fields': [{'pointer': '/0/role', 'item': handle, 'fieldKey': None, 'evidence': ['S1'], 'effectiveCells': ['E1']}],
        'lineage': [{'kind': 'add', 'parents': [], 'children': ['proj']}, {'kind': 'split', 'parents': ['H1'], 'children': ['a']}],
        'relations': [{'relation': {'kind': 'new', 'key': 'r'}, 'kind': 'owned_by', 'subject': keyed, 'target': handle, 'evidence': []},
            {'relation': {'kind': 'new', 'key': 'q'}, 'kind': 'owned_by', 'subject': keyed, 'target': keyed, 'evidence': []}]}, nothing)
    assert stripped['fields'] == [{'pointer': '/0/role', 'item': None, 'fieldKey': None, 'evidence': ['S1'], 'effectiveCells': None}]
    assert stripped['lineage'] == [{'kind': 'add', 'parents': [], 'children': ['proj']}] and len(stripped['relations']) == 1
    assert strip_unoffered_bookkeeping({'payload': [], 'relations': [1]}, None) == {'payload': [], 'relations': [1]}


# I4 (2026-10-25): a repair that still states a value no source line states loses that value and keeps the block.
from packages.resume_core.template_completion import without_unbound


def test_unbound_values_leave_the_payload_and_later_pointers_move_down():
    payload = [{'company': 'North', 'tasks': [{'value': 'Kept first.'}, {'value': 'Invented task.'}, {'value': 'Kept last.'}]},
        {'company': 'South', 'role': 'Invented role'}]
    fields = [{'pointer': '/0/tasks/2/value', 'fieldKey': 'value', 'evidence': ['S3'], 'item': None, 'effectiveCells': None},
        {'pointer': '/0/tasks/1/value', 'fieldKey': 'value', 'evidence': ['S9'], 'item': None, 'effectiveCells': None},
        {'pointer': '/1/role', 'fieldKey': 'role', 'evidence': [], 'item': None, 'effectiveCells': None}]
    instances = {'/0/company': [], '/0/tasks/0/value': [], '/0/tasks/1/value': [], '/0/tasks/2/value': [], '/1/company': [], '/1/role': []}
    reduced, dropped = without_unbound({'payload': payload, 'fields': fields, 'discoveries': None},
        [('/0/tasks/1/value', 'value'), ('/1/role', 'role')], instances)
    assert [task['value'] for task in reduced['payload'][0]['tasks']] == ['Kept first.', 'Kept last.']
    assert reduced['payload'][1]['role'] is None and payload[1]['role'] == 'Invented role'
    assert [(entry['pointer'], entry['evidence']) for entry in reduced['fields']] == [('/0/tasks/1/value', ['S3'])]
    assert dropped == [{'pointer': '/0/tasks/1/value', 'fieldKey': 'value', 'text': 'Invented task.'},
        {'pointer': '/1/role', 'fieldKey': 'role', 'text': 'Invented role'}]
