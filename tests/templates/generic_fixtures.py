"""Scripted Generic replies: each block's payload, with the exact source phrase every value cites."""

from functools import cache

from packages.resume_core.template_identity import _binding_instances, _bound_root, capture_span, empty_value, payload_value
from packages.resume_core.templates.builtin_mapping import item_root
from packages.resume_core.templates.compiler import compile_template
from packages.resume_core.templates.projection import pointer_tokens
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.storage_fixtures import source_fixture


@cache
def generic_package():
    return compile_template(BUNDLED_TEMPLATE)


def pointer_of(tokens):
    return ''.join('/' + token.replace('~', '~0').replace('/', '~1') for token in tokens)


def natural(pointer):
    return [(0, int(token), '') if token.isdecimal() else (1, 0, token) for token in pointer_tokens(pointer)]


def span(src, phrase):
    unit = next((unit for unit in src.units if phrase in unit.text), None)
    assert unit is not None, 'phrase is not in the source: ' + phrase
    start = unit.text.index(phrase)
    return capture_span(src, unit, start, start + len(phrase)).model_dump(by_alias=True)


def phrases(payload, pointer, value, cites):
    if pointer in cites:
        cited = cites[pointer]
        return [cited] if isinstance(cited, str) else list(cited)
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict) and isinstance(value.get('raw'), str):
        return [value['raw']]
    parent = payload_value(payload, pointer_of(pointer_tokens(pointer)[:-1]))
    if isinstance(value, bool) and isinstance(parent, dict) and isinstance(parent.get('raw'), str):
        return [parent['raw']]
    raise AssertionError('no cited phrase for ' + pointer)


def block_reply(block, payload, src, cites=None, request=None):
    """One discovery per item root, one field per bound value and the configured owner links; a repair selects
    the items its request captured."""
    cites = cites or {}
    instances = sorted(_binding_instances(payload, block.bindings), key=lambda value: (natural(value[0]), value[1], value[2]))
    if not instances:
        assert empty_value(payload), 'payload has values outside the compiled bindings'
        return {'schemaVersion': 1, 'payload': payload, 'discoveries': [], 'fields': [], 'lineage': [], 'relations': []}
    keys, discoveries, fields, evidence = {}, [], [], {}
    for pointer, semantic, field in instances:
        root = tuple(_bound_root(pointer, semantic, field, block.bindings))
        key = keys.get((semantic, root))
        if key is None:
            key = keys[(semantic, root)] = 'item-' + str(len(keys))
            discoveries.append({'key': key, 'semanticType': semantic, 'pointer': pointer_of(root)})
        value = payload_value(payload, pointer)
        cited = [] if empty_value(value) else [span(src, phrase) for phrase in phrases(payload, pointer, value, cites)]
        evidence.setdefault(key, []).extend(cited)
        fields.append({'item': {'kind': 'discovery_key', 'key': key}, 'fieldKey': field, 'pointer': pointer,
            'evidence': cited, 'effectiveCellIds': []})
    roots = {root: key for (_semantic, root), key in keys.items()}
    relations, linked = [], set()
    for (semantic, root), key in keys.items():
        for binding in block.bindings:
            pattern = item_root(binding, block.bindings)
            if (binding.semantic_type != semantic or binding.relation is None or len(pattern) != len(root)
                    or any(expected not in {'*', actual} for expected, actual in zip(pattern, root))
                    or (key, binding.relation.kind) in linked):
                continue
            target = tuple(root[index] if token == '*' else token
                for index, token in enumerate(pointer_tokens(binding.relation.subject_pointer)))
            linked.add((key, binding.relation.kind))
            relations.append({'relation': {'kind': 'discovery_key', 'key': 'link-' + key}, 'kind': binding.relation.kind,
                'subject': {'kind': 'discovery_key', 'key': key}, 'target': {'kind': 'discovery_key', 'key': roots[target]},
                'evidence': evidence[key] or evidence[roots[target]]})
    reply = {'schemaVersion': 1, 'payload': payload, 'discoveries': discoveries, 'fields': fields,
        'lineage': [{'kind': 'add', 'parents': [], 'children': [value['key'] for value in discoveries]}], 'relations': relations}
    if (request or {}).get('slot', 'initial') == 'initial':
        return reply
    # Other blocks' items can be captured too; only this block's own types are its earlier items.
    types = {binding.semantic_type for binding in block.bindings}
    captured = {value['key']: value for value in request.get('capturedHandles', []) if value.get('semanticType') in types}
    # A repair selects the items and links its earlier attempt allocated, by handle and relation id.
    known = {(value['kind'], value['subjectId'], value['targetId']): value['id'] for value in request['capturedRelations']}
    for field in reply['fields']:
        field['item'] = {'kind': 'handle', 'itemHandle': captured[field['item']['key']]['itemHandle']}
    for relation in reply['relations']:
        subject, target = captured[relation['subject']['key']], captured[relation['target']['key']]
        relation['subject'] = {'kind': 'handle', 'itemHandle': subject['itemHandle']}
        relation['target'] = {'kind': 'handle', 'itemHandle': target['itemHandle']}
        relation['relation'] = {'kind': 'relation_id', 'relationId': known[(relation['kind'], subject['recordId'], target['recordId'])]}
    reply['discoveries'], reply['lineage'] = [], []
    return reply


def date(raw, year, month=None):
    return {'raw': raw, 'year': year, 'month': month}


def period(raw, start, end, ongoing):
    return {'raw': raw, 'start': start, 'end': end, 'ongoing': ongoing}


def job(company, role, when, *, project=None, technologies=(), tasks=(), results=(), details=None):
    return {'company': company, 'project': project, 'period': when, 'technologies': [{'display': name} for name in technologies],
        'role': role, 'role_details': details, 'tasks': [{'value': text} for text in tasks],
        'results': [{'value': text} for text in results]}


def identity(name, profession, family, cite):
    return {'name': name, 'profession': profession, 'role_family': {'family': family}}, {'/role_family/family': cite}


def terms(*names):
    return {'items': list(names)}, {}


def f01(rewrite):
    table = {
        'identity': identity('Alex Example', 'Backend engineer', 'other', 'Backend engineer'),
        'projects': ([job('Example Labs', 'backend engineer', period('03.2020–11.2023', date('03.2020', 2020, 3),
            date('11.2023', 2023, 11), False), technologies=['Python'], tasks=['Implemented queue processing.'],
            results=['Our team reduced median latency from 800 ms to 500 ms.'])], {}),
        'programming': terms('Python'),
    }
    if rewrite:
        table['summary'] = ({'text': 'Backend engineer who implemented queue processing.'},
            {'/text': ['Backend engineer', 'Implemented queue processing.']})
    return table


def f02(_rewrite):
    return {
        'identity': identity('Alex Example', 'backend engineer', 'other', 'backend engineer'),
        'projects': ([job('Example Labs', 'backend engineer', period('2020–2023', date('2020', 2020), date('2023', 2023), False),
            technologies=['Python'], tasks=['Implemented queue processing.'])], {}),
        'programming': terms('Python'),
    }


def f03(_rewrite):
    # The model gives the unowned paragraph to an arbitrary employer; the ownership review rejects that link.
    return {
        'identity': identity('Alex Example', 'engineer', 'other', 'engineer'),
        'projects': ([job('Example Labs', 'engineer', period('2020–2023', date('2020', 2020), date('2023', 2023), False)),
            job('Second Works', 'engineer', period('2024–present', date('2024', 2024), None, True),
                results=['Improved release reliability.'])],
            {'/0/role': 'Example Labs — engineer', '/1/role': 'Second Works — engineer'}),
    }


def f04(_rewrite):
    jobs = [job('Early Systems', 'engineer', period('2013–2015', date('2013', 2013), date('2015', 2015), False), technologies=['Perl']),
        job('Year Boundary', 'engineer', period('2014–2016', date('2014', 2014), date('2016', 2016), False)),
        job('Month Boundary', 'engineer', period('2015–2016-10', date('2015', 2015), date('2016-10', 2016, 10), False)),
        job('Current Systems', 'engineer', period('2020–present', date('2020', 2020), None, True), technologies=['Python'])]
    cites = {}
    for index, value in enumerate(jobs):
        line = value['company']
        cites.update({'/' + str(index) + suffix: line for suffix in ['/role', '/period/start', '/period/end', '/period/ongoing']})
    return {
        'identity': identity('Alex Example', 'engineer', 'other', 'Early Systems'),
        'projects': (jobs, {**cites, '/0/role': 'Early Systems', '/1/role': 'Year Boundary'}),
        'programming': terms('Perl', 'Python'),
    }


def f06(_rewrite, family='business_analyst'):
    table = {
        'identity': identity('Alex Example', 'Business analyst', family, 'Business analyst'),
        'focus': ([{'technology': 'Python', 'experience': '10 months'}, {'technology': 'SQL', 'experience': 'about 2.5 years'},
            {'technology': 'UnknownTool', 'experience': '7 weeks'}], {}),
        'education': ([{'institution': 'Example University', 'graduation_year': date('2019', 2019), 'place': None,
            'specialization': 'Information Systems', 'degree': 'BSc'}], {}),
        'courses': ([{'school': 'Example Academy', 'title': 'Queue Design', 'year': date('2021', 2021)},
            {'school': 'Systems School', 'title': 'Reliability Basics', 'year': date('2022', 2022)}], {}),
        'languages': ([{'name': 'English', 'level': 'working proficiency', 'note': None}], {}),
        'portfolio': ([{'name': 'Portfolio', 'url': 'https://example.org/portfolio'}], {}),
    }
    if family in {'system_analyst', 'business_analyst', 'tester', 'designer'}:
        table['role_tools'] = terms('Python', 'SQL', 'UnknownTool')
    else:
        table['programming'] = terms('Python')
        table['data_and_tools'] = terms('SQL', 'UnknownTool')
    return table


def f07(_rewrite):
    src, _raw = source_fixture('F07')
    lines = src.units[0].text.splitlines()
    tasks = [line for line in lines if line.startswith('PROJECT-MARKER-')]
    courses = [line for line in lines if line.startswith('SIDEBAR-MARKER-')]
    url = next(line for line in lines if line.startswith('https://'))
    name, title = lines[0], lines[1]
    return {
        'identity': identity(name, title, 'other', title),
        'projects': ([job(None, title, period(None, None, None, None), tasks=tasks)], {}),
        'courses': ([{'school': None, 'title': line, 'year': None} for line in courses], {}),
        'portfolio': ([{'name': None, 'url': url}], {}),
    }


F10_RESULT = 'Reduced median latency by 80%.'


def f10(_rewrite):
    return {
        'identity': identity('Alex Example', 'Backend engineer', 'other', 'Backend engineer'),
        'focus': ([{'technology': 'Python', 'experience': '3 years'}], {}),
        'education': ([{'institution': 'Example Institute', 'graduation_year': None, 'place': None, 'specialization': None,
            'degree': None}], {}),
        'courses': ([{'school': 'Example Academy', 'title': 'Queue Design', 'year': date('2021', 2021)}], {}),
        'location': ({'city': 'Example City', 'country': 'Example Country', 'timezone': 'UTC+1'}, {}),
        'languages': ([{'name': 'English', 'level': None, 'note': None}], {}),
        'opensource': ([{'name': 'Queue Tools', 'url': 'https://example.org/queue-tools'}], {}),
        'projects': ([
            job('Old Systems', 'engineer', period('2010–2012', date('2010', 2010), date('2012', 2012), False), technologies=['Perl']),
            job('Example Labs', 'backend engineer', period('03.2020–11.2023', date('03.2020', 2020, 3), date('11.2023', 2023, 11), False),
                project={'name': 'Queue Platform', 'description': 'Message queue platform for internal services.'},
                technologies=['Python', 'PostgreSQL', 'Docker'], tasks=['Implemented queue processing.'],
                # The rewrite claims more than the source states; the review rejects it.
                results=['Reduced median latency by 80% for all services.'])],
            {'/0/role': 'Old Systems', '/0/period/start': 'Old Systems', '/0/period/end': 'Old Systems',
                '/1/project/description': 'Product: message queue platform for internal services.',
                '/1/technologies/0/display': 'Python, PostgreSQL, Docker', '/1/results/0/value': F10_RESULT}),
        'career_highlights': ({'items': ['Mentored five engineers across teams.']}, {}),
        'programming': terms('Python', 'Perl'),
        'data_and_tools': terms('PostgreSQL'),
        'infrastructure': terms('Docker'),
        'summary': ({'text': 'Backend engineer focused on reliable queue systems.'}, {}),
    }


TABLES = {'F01': f01, 'F02': f02, 'F03': f03, 'F04': f04, 'F06': f06, 'F07': f07, 'F10': f10}
F10_REJECTED = 'Reduced median latency by 80% for all services.'


def f10_review(check):
    # The rewritten result claims more than its own source line states.
    return 'violation' if check.get('ruleId') == 'projects-support' and check.get('value') == F10_REJECTED else None


REVIEWS = {'F10': f10_review}


def satisfied(value, verdict=None):
    """Every check satisfied unless the case's verdict names another disposition for it."""
    results = []
    checks = value.get('semanticContext', {}).get('checks', [])
    for target, check in zip(value['targets'], checks, strict=True):
        disposition = verdict(check) if verdict else None
        results.append({'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': disposition or 'satisfied',
            'reason': '' if disposition is None else 'Not supported by the cited source.', 'evidence': [], 'actionable': False})
    return {'results': results}


def generic_script(src, table, verdict=None):
    package = generic_package()
    blocks = {block.id: block for block in package.definition.blocks}
    def script(_request, value):
        if 'targets' in value:
            return satisfied(value, verdict)
        block = blocks[value['declaration']['id']]
        if block.id in table:
            payload, cites = table[block.id]
        else:
            payload, cites = ([] if block.view.mode == 'items' else empty_object(block)), {}
        return block_reply(block, payload, src, cites, value)
    return script


def empty_object(block):
    full = next(value.full_schema for value in generic_package().blocks if value.id == block.id)
    properties = full.get('properties') or full['$defs'][full['$ref'].rsplit('/', 1)[1]]['properties']
    return {key: [] if (schema.get('type') == 'array' or '$ref' in schema and schema['$ref'].endswith('/texts')) else None
        for key, schema in properties.items()}


async def generic_import(root, name, *, rewrite=True, verdict=None, table=None, cap=60, wrap=None):
    """A published Generic import of one synthetic fixture through the coordinator and the real materializer; wrap
    changes the scripted answers."""
    from packages.resume_core.background_limits import import_seconds
    from packages.resume_core.project_limits import finalization_seconds
    from packages.resume_core.templates.operations import derive_task
    from tests.templates.test_template_employment import EmploymentFixture
    src, raw = source_fixture(name)
    fixture = EmploymentFixture(root, captured=generic_package(), src=src, original_bytes=raw, cap=cap, fallback=False)
    fixture.command.capture.allow_text_rewrite = rewrite
    # The default Settings limits hold about thirty durable calls and the publication on the real clock (D096).
    fixture.command.capture.policy.processing_seconds = import_seconds()
    fixture.command.capture.policy.finalization_seconds = finalization_seconds()
    fixture.pipeline.derive = derive_task
    script = generic_script(src, table or TABLES[name](rewrite), verdict or REVIEWS.get(name))
    fixture.transport.scripted = wrap(script) if wrap else script
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    return fixture, result, fixture.current(), {src.id: raw}


async def export_through_service(tmp_path, workspace, originals):
    """One export through the actual HTTP route and captured worker; the stored attempt completes with the captured package."""
    from types import SimpleNamespace
    import httpx
    from packages.resume_core.template_export import snapshot_identity
    from resume_api.jobs.service import JobService
    from tests.templates.test_template_api import application, isolated_service
    service, identifier = isolated_service(tmp_path, workspace, originals)
    jobs = JobService(service, None, lambda: SimpleNamespace(ready=False), enabled=False, template_cleanup_verified=lambda: True)
    await jobs.start()
    try:
        before = service.storage.read_committed(identifier)[0]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(service)), base_url='http://foldcv.test') as client:
            response = await client.post('/v1/rich/projects/' + identifier + '/export',
                json={'schemaVersion': 1, 'snapshot': snapshot_identity(before).model_dump(mode='json', by_alias=True)})
        assert response.status_code == 200, response.text
        attempt = service.storage.read_committed(identifier)[0].project.exports[-1]
        assert attempt.state == 'completed' and attempt.package_hash == before.project.template_package.package_hash
        return response.content
    finally:
        await service.shutdown()
        await jobs.shutdown()


def direct_generic(name, blocks, *, rewrite=True, table=None):
    """Admission and assembly of the given blocks without the durable store, for rendering cases that do not need
    the import record; every review answers satisfied."""
    import json
    from itertools import count
    from packages.resume_core.models.template_import import ReviewInputRecord
    from packages.resume_core.template_admission import admit_proposal
    from packages.resume_core.template_assembly import assemble_template
    from packages.resume_core.template_import import (admit_operation, capture_task_input, digest, dispatch_attempt,
        record_return, reserve_attempt, task_in)
    from packages.resume_core.template_proposals import parse_proposal
    from packages.resume_core.template_review import make_review_input, record_review
    from tests.templates.evidence_references import by_reference
    from tests.templates.pipeline_fixtures import NOW, cleaned, owner, setup_operation, source_draft, usage
    package = generic_package()
    src, raw = source_fixture(name)
    table, declarations = table or TABLES[name](rewrite), {block.id: block for block in package.definition.blocks}
    operation, _command, _package, _src, facts = setup_operation(captured=package, src=src, allow_text_rewrite=rewrite,
        cap=2 * len(blocks))
    operation, serial = admit_operation(operation, NOW), count(1)
    for block_id in blocks:
        identifier = next(task.id for task in operation.tasks if task.block_id == block_id)
        operation = capture_task_input(operation, identifier, {'protocol': 'template_import_v1',
            'sources': [src.model_dump(mode='json', by_alias=True)], 'effectiveCells': [], 'tools': []}, [], NOW)
        task = task_in(operation, identifier)
        payload, cites = table[block_id]
        operation, attempt = reserve_attempt(operation, task.id, 'initial', task.input_hash, operation.capture.primary,
            owner(next(serial)), NOW)
        operation = dispatch_attempt(operation, attempt, NOW)
        operation = record_return(operation, attempt, json.dumps({'payload': block_reply(declarations[block_id], payload, src, cites)}),
            'completed', usage(), cleaned(), returned_at=NOW)
        operation, facts, proposal = parse_proposal(operation, attempt, package, [src], facts)
        assert proposal.state == 'provisional', proposal.errors
        review = make_review_input(operation, proposal, package, [src], operation.capture.primary, effective_cells=[],
            semantic_context={'capturedTaskInput': next(value.value for value in operation.task_inputs if value.task_id == task.id)})
        operation, checked = reserve_attempt(operation, task.id, 'review', digest(review), review.policy, owner(next(serial)), NOW)
        operation.review_inputs.append(ReviewInputRecord(id='review-input-' + block_id, attemptId=checked, inputHash=digest(review),
            value=review))
        operation.attempts[-1].review_input_record_id = 'review-input-' + block_id
        operation = dispatch_attempt(operation, checked, NOW)
        results = {'results': [{'ruleId': target.rule_id, 'targetId': target.target_id, 'disposition': 'satisfied', 'reason': '',
            'evidence': [], 'actionable': False} for target in review.targets]}
        operation = record_return(operation, checked, json.dumps({'payload': by_reference(results, review)}), 'completed', usage(),
            cleaned(), returned_at=NOW)
        operation, receipt = record_review(operation, checked, [src], NOW)
        operation, facts = admit_proposal(operation, proposal.id, receipt.id, package, [src], facts, expected_revisions={},
            expected_relation_revisions={})
    return assemble_template(source_draft(operation, facts, captured=package, src=src), operation), {src.id: raw}
