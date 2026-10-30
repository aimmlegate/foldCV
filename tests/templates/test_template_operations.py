"""Deterministic operations read admitted facts: the F04 fifteen-year partition and declared period formatting."""

import json
from types import SimpleNamespace

import pytest

from packages.resume_core.models.rich_facts import EmploymentRecord
from packages.resume_core.models.template_import import ImportCapture
from packages.resume_core.template_identity import capture_span
from packages.resume_core.template_import import spent_calls
from packages.resume_core.templates.compiler import compile_bytes
from packages.resume_core.templates.models import PartitionOperation
from packages.resume_core.templates.operations import OperationContext, derive_task, partition_employment
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.employment_fixtures import employment_package, employment_source
from tests.templates.pipeline_fixtures import setup_operation
from tests.templates.template_runtime_fixtures import EmploymentFixture


EXPECTED = json.loads(open('tests/fixtures/synthetic/templates/expected.json').read())
JOBS = [('Early Systems', (2008, None), (2010, None), False, 'Perl'), ('Year Boundary', (2009, None), (2011, None), False, None),
    ('Month Boundary', (2010, None), (2011, 10), False, None), ('Current Systems', (2020, None), None, True, 'Python')]


def partial(value):
    if value is None:
        return None
    year, month = value
    return {'precision': 'month' if month else 'year', 'year': year, 'month': month, 'day': None}


def field(value, raw):
    return {'value': value, 'rawText': raw, 'status': 'known' if value is not None else 'unknown', 'revision': 1, 'pendingRawText': None}


def records():
    return [EmploymentRecord.model_validate({'id': 'job-' + str(index), 'revision': 1, 'origin': 'source', 'evidence': [],
        'kind': 'employment', 'employer': field(name, name), 'role': field('engineer', 'engineer'),
        'periods': [{'id': 'period-' + str(index), 'revision': 1, 'start': field(partial(start), str(start[0])),
            'end': field(partial(end), '' if end is None else str(end[0])), 'present': field(ongoing, str(ongoing).lower()),
            'evidence': []}]}) for index, (name, start, end, ongoing, _technology) in enumerate(JOBS)]


def capture(*, rewrite=True, as_of=(2026, 10, 21)):
    year, month, day = as_of
    value = setup_operation(allow_text_rewrite=rewrite)[1].capture.model_dump(mode='json', by_alias=True)
    value['formattingAsOf'] = {'precision': 'day' if day else 'month' if month else 'year', 'year': year, 'month': month, 'day': day}
    return ImportCapture.model_validate(value)


def window(years=15):
    return PartitionOperation.model_validate({'id': 'project-window', 'kind': 'partition_employment', 'version': 1,
        'inputs': [{'kind': 'block', 'id': 'employment-view'}], 'depends_on': [],
        'parameters': {'years': years, 'detailed': 'employment-view', 'compact': 'old-projects'}})


def names(identifiers):
    by_id = {record.id: record.employer.value for record in records()}
    return [by_id[identifier] for identifier in identifiers]


@pytest.mark.parametrize('as_of', [(2026, 10, 21), (2026, 10, None)])
def test_partition_compacts_only_employment_wholly_older_than_the_cutoff(as_of):
    result = partition_employment(window(), OperationContext(capture(as_of=as_of), SimpleNamespace(records=records()),
        handles={'job-0': 'handle-0'}))
    assert names(result.value['compact']) == EXPECTED['F04']['compact']
    assert names(result.value['detailed']) == EXPECTED['F04']['detailed']
    assert result.value['cutoff'] == ('2011-10-21' if as_of[2] else '2011-10-01') and result.item_handles == ('handle-0',)


def test_disabled_rewriting_or_unknown_end_keeps_employment_detailed():
    disabled = partition_employment(window(), OperationContext(capture(rewrite=False), SimpleNamespace(records=records())))
    assert disabled.value['compact'] == [] and len(disabled.value['detailed']) == 4
    unknown = records()[0].model_copy(deep=True)
    unknown.periods[0].end = unknown.periods[0].end.model_copy(update={'value': None, 'status': 'unknown', 'raw_text': ''})
    assert partition_employment(window(), OperationContext(capture(), SimpleNamespace(records=[unknown]))).value['compact'] == []


def history_package():
    config = employment_package().definition.model_dump(mode='json', by_alias=True)
    view = json.loads(json.dumps(config['blocks'][0]['view']))
    view.update(mode='object', heading='band', title={'en': 'OTHER PROJECTS'},
        nodes=[{'type': 'join_items', 'field': '/items', 'separator': ', ', 'style': 'body'}])
    config['operations'] = [
        {'id': 'project-window', 'kind': 'partition_employment', 'version': 1, 'inputs': [{'kind': 'block', 'id': 'employment-view'}],
            'depends_on': [], 'parameters': {'years': 15, 'detailed': 'employment-view', 'compact': 'old-projects'}},
        {'id': 'source-periods', 'kind': 'format_period', 'version': 1, 'inputs': [{'kind': 'source', 'id': 'all'}],
            'depends_on': [], 'parameters': {'separator': ' – ', 'ongoing_label': {'en': 'present'}}}]
    config['blocks'].append({'id': 'old-projects', 'mode': 'derived', 'selectors': [{'kind': 'source', 'id': 'all'}],
        'content_schema': {'type': 'object', 'additionalProperties': False, 'required': ['items'],
            'properties': {'items': {'type': 'array', 'items': {'type': 'string'}}}},
        'bindings': [], 'extract': [], 'rewrite': {'fields': [], 'instructions': []}, 'checks': [], 'depends_on': [],
        'operation': 'project-window', 'when': None, 'placement': {'region': 'main', 'order': 2}, 'view': view})
    return compile_bytes(json.dumps(config).encode(), BUNDLED_TEMPLATE.parent, original_format='json')


def history_proposal(src):
    lines = src.units[0].text.splitlines()
    def span(text):
        unit = src.units[0]
        offset = unit.text.index(text)
        return capture_span(src, unit, offset, offset + len(text)).model_dump(by_alias=True)
    def date(value):
        return None if value is None else {'raw': str(value[0]) + ('-' + str(value[1]) if value[1] else ''),
            'year': value[0], 'month': value[1]}
    payload, discoveries, fields, relations = [], [], [], []
    for index, (name, start, end, ongoing, technology) in enumerate(JOBS):
        evidence = [span(next(line for line in lines if line.startswith(name)))]
        payload.append({'company': name, 'role': 'engineer', 'period': {'raw': None, 'start': date(start), 'end': date(end),
            'ongoing': ongoing}, 'description': None, 'tasks': [], 'results': [],
            'technologies': [{'display': technology}] if technology else []})
        key, root = 'job-' + str(index), '/' + str(index)
        discoveries.append({'key': key, 'semanticType': 'employment', 'pointer': root})
        for name_, pointer, value in [('company', '/company', name), ('role', '/role', 'engineer'), ('start', '/period/start', start),
                ('end', '/period/end', end), ('present', '/period/ongoing', ongoing)]:
            fields.append({'item': {'kind': 'discovery_key', 'key': key}, 'fieldKey': name_, 'pointer': root + pointer,
                'evidence': [] if value is None else evidence, 'effectiveCellIds': []})
        if technology:
            discoveries.append({'key': key + '-technology', 'semanticType': 'technology', 'pointer': root + '/technologies/0'})
            fields.append({'item': {'kind': 'discovery_key', 'key': key + '-technology'}, 'fieldKey': 'display',
                'pointer': root + '/technologies/0/display', 'evidence': evidence, 'effectiveCellIds': []})
            relations.append({'relation': {'kind': 'discovery_key', 'key': key + '-owner'}, 'kind': 'owned_by',
                'subject': {'kind': 'discovery_key', 'key': key + '-technology'}, 'target': {'kind': 'discovery_key', 'key': key},
                'evidence': evidence})
    return {'schemaVersion': 1, 'payload': payload, 'discoveries': discoveries, 'fields': fields,
        'lineage': [{'kind': 'add', 'parents': [], 'children': [value['key'] for value in discoveries]}], 'relations': relations}


@pytest.mark.asyncio
@pytest.mark.parametrize('rewrite', [True, False])
async def test_partition_view_shows_detailed_employment_and_compact_names_while_retaining_facts(tmp_path, rewrite):
    src, raw = employment_source('F04')
    fixture = EmploymentFixture(tmp_path, captured=history_package(), src=src, original_bytes=raw, cap=4, fallback=False)
    fixture.command.capture.allow_text_rewrite = rewrite
    fixture.pipeline.derive = derive_task
    def script(_request, value):
        if 'targets' in value:
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
                'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}
        return history_proposal(src)
    fixture.transport.scripted = script
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.publication.state == 'saved' and spent_calls(result) == 2
    states = {task.block_id: task.state for task in result.tasks}
    assert states == {'employment-view': 'accepted', 'project-window': 'accepted', 'source-periods': 'accepted',
        'old-projects': 'accepted' if rewrite else 'empty'}
    current = fixture.current().project
    assert sorted(record.employer.value for record in current.facts.records if record.kind == 'employment') == sorted(job[0] for job in JOBS)
    assert {record.display.value for record in current.facts.records if record.kind == 'technology'} == set(EXPECTED['F04']['allSkills'])
    texts = [''.join(part.text for part in block.content) for block in current.document.blocks()]
    shown = [name for name, *_rest in JOBS if name in texts]
    assert texts.count('Early Systems') == 1 and len(shown) == 4
    if rewrite:
        # Detailed employment keeps its section; the old job appears once, under the compact heading.
        heading = texts.index('OTHER PROJECTS')
        assert texts.index('Early Systems') > heading > max(texts.index(name) for name in EXPECTED['F04']['detailed'])
    else:
        assert 'OTHER PROJECTS' not in texts
    assert '2009 – 2011' in texts and '2020 – present' in texts and '2010 – 2011-10' in texts


@pytest.mark.asyncio
async def test_an_old_job_with_no_employer_to_show_stays_detailed_instead_of_leaving_the_document(tmp_path):
    src, raw = employment_source('F04')
    fixture = EmploymentFixture(tmp_path, captured=history_package(), src=src, original_bytes=raw, cap=4, fallback=False)
    fixture.pipeline.derive = derive_task
    def script(_request, value):
        if 'targets' in value:
            return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
                'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}
        proposal = history_proposal(src)
        proposal['payload'][0]['company'] = None
        next(item for item in proposal['fields'] if item['pointer'] == '/0/company')['evidence'] = []
        return proposal
    fixture.transport.scripted = script
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.publication.state == 'saved'
    current = fixture.current().project
    old = next(record for record in current.facts.records if record.kind == 'employment' and record.employer.value is None)
    texts = [''.join(part.text for part in block.content) for block in current.document.blocks()]
    # Its period shows under the detailed block; the compact list has nothing to name it by.
    assert '2008 – 2010' in texts and 'OTHER PROJECTS' not in texts and old.periods
