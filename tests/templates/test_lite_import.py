"""The lite import through the pipeline: its scheme reads the CV with its own calls, and code answers every request
the pipeline would send to a model. The scheme's calls are replayed from one live run on an invented CV."""

import asyncio
import json
from pathlib import Path

import pytest

from packages.resume_core.extraction.parser import extract
from packages.resume_core.project_limits import finalization_seconds, import_seconds
from packages.resume_core.sources import canonical_source
from packages.resume_core.templates.operations import derive_task
from resume_api.importer import lite_import
from resume_api.providers.content import ContentFailure, ReportedUsage
from tests.templates.generic_fixtures import generic_package
from tests.templates.scripted_template_provider import ScriptedTemplateProvider
from tests.templates.template_runtime_fixtures import ControlledTransport, EmploymentFixture
from tests.templates.test_template_import_app import app_client, operation_of, saved, upload

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'synthetic' / 'lite'


class StoredCalls:
    """The scheme's calls answered from a stored run, by kind and block, in call order."""
    envelope = False     # the run was Claude's: its replies have no {"payload"} envelope

    def __init__(self, name, fail=()):
        self.rows, self.replies, self.fail = [], {}, set(fail)
        for call in json.loads((FIXTURES / (name + '.json')).read_text()):
            self.replies.setdefault((call['kind'], call['block']), []).append(call)

    def call(self, kind, block, _prompt, _schema):
        held = self.replies.get((kind, block)) or []
        if not held or kind in self.fail:
            row = {'kind': kind, 'block': block, 'errorCode': 'INVALID_RESULT', 'usage': None}
            self.rows.append(row)
            return None, row
        call = held.pop(0)
        row = {'kind': kind, 'block': block, 'errorCode': None, 'usage': ReportedUsage(*call['usage'], True)}
        self.rows.append(row)
        return call['reply'], row


class LiteTransport(ControlledTransport):
    """The controlled transport with the two things a lite import asks of a transport."""

    def __init__(self, fixture, stored):
        super().__init__(fixture)
        self.stored, self.model_calls = stored, 0

    def lite_calls(self, _model, _cancel, _remaining):
        return self.stored

    def generate(self, request, cancel):
        lite = lite_import.LITE.get()
        if lite is not None:
            self.calls.append(request.request_value)
            return lite_import.generate(request, lite)
        self.model_calls += 1
        return super().generate(request, cancel)


def lite_run(tmp_path, name, fail=()):
    data = (FIXTURES / (name + '.docx')).read_bytes()
    source = canonical_source(extract(data, name + '.docx'))
    fixture = EmploymentFixture(tmp_path, captured=generic_package(), src=source, original_bytes=data, cap=80,
                                fallback=False, concurrency=1)
    fixture.transport = LiteTransport(fixture, StoredCalls(name, fail))
    fixture.pipeline = fixture.fresh_pipeline()
    fixture.pipeline.derive = derive_task
    capture = fixture.command.capture
    capture.allow_text_rewrite, capture.policy.lite = False, True
    capture.policy.processing_seconds, capture.policy.finalization_seconds = import_seconds(), finalization_seconds()
    operation = asyncio.run(fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted))
    return fixture, operation


def jobs(fixture):
    return [(record.employer.raw_text, record.role.raw_text) for record in fixture.current().project.facts.records
            if record.kind == 'employment']


def document_text(fixture):
    found = []

    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get('text'), str):
                found.append(value['text'])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(fixture.current().project.model_dump(mode='json', by_alias=True)['document'])
    return ' '.join(found)


@pytest.fixture(scope='module')
def promotions(tmp_path_factory):
    return lite_run(tmp_path_factory.mktemp('promotions'), 'promotions')


def test_a_lite_import_publishes_the_schemes_result_with_no_model_call_of_the_pipeline(promotions):
    fixture, operation = promotions
    assert operation.state == 'published'
    # Every request of the pipeline was answered by code: extractions and reviews, no repair, no fallback.
    assert fixture.transport.model_calls == 0
    assert {attempt.slot for attempt in operation.attempts} == {'initial', 'review'}
    assert {attempt.outcome for attempt in operation.attempts} == {'completed'}
    assert not [issue for issue in operation.issues if issue.code == 'IMPORT_SOURCE_FALLBACK']
    # Three roles at one employer are three jobs, each with its own role (the narrow question cut the entry).
    assert jobs(fixture) == [('АО «Северная линия»', 'Руководитель группы разработки'),
                             ('АО «Северная линия»', 'Ведущий разработчик'), ('АО «Северная линия»', 'Разработчик'),
                             ('Томский технический лицей', 'Преподаватель курса по Java (по совместительству)')]
    # The record carries the tokens the scheme's own calls spent.
    spent = [row['usage'] for row in fixture.transport.stored.rows]
    assert sum(attempt.usage.input_tokens for attempt in operation.attempts) == sum(usage.input_tokens for usage in spent)
    assert sum(attempt.usage.output_tokens for attempt in operation.attempts) == sum(usage.output_tokens for usage in spent)


def test_a_lite_import_names_the_lines_no_field_took(promotions):
    _fixture, operation = promotions
    notices = [issue.message for issue in operation.issues if issue.code == 'IMPORT_SOURCE_UNUSED']
    assert notices and all(message.startswith('Строки резюме без поля в шаблоне: ') for message in notices)


def test_a_project_with_no_employer_role_or_period_is_still_a_card(tmp_path):
    fixture, operation = lite_run(tmp_path, 'junior')
    assert operation.state == 'published'
    # One job and two study projects: the projects state no employer, no role and no dates.
    assert jobs(fixture) == [('ООО «Первый шаг»', 'Стажёр-разработчик'), ('', ''), ('', '')]
    text = document_text(fixture)
    assert 'Бот «Расписание»' in text and 'Сайт «Книжная полка»' in text


def test_a_lite_import_whose_map_fails_shows_the_source_lines_of_each_block(tmp_path):
    fixture, operation = lite_run(tmp_path, 'promotions', fail={'map'})
    assert operation.state == 'published'
    assert fixture.transport.model_calls == 0
    assert any(issue.code == 'IMPORT_SOURCE_FALLBACK' for issue in operation.issues)
    assert jobs(fixture) == []


class RefusingProvider(ScriptedTemplateProvider):
    """Refuses the scheme's own calls (they carry no captured request) and counts every call a task makes."""

    def generate(self, request, files, cancel):
        if request.request_value is None:
            self.calls.append({'kind': 'lite'})
            raise ContentFailure('REFUSED', logical_attempts=1, cleanup_verified=True, dispatch_witness={'transport': 'scripted'})
        return super().generate(request, files, cancel)


@pytest.mark.asyncio
async def test_a_start_with_lite_captures_a_lite_import_and_no_task_calls_a_model(tmp_path):
    provider = RefusingProvider()
    async with app_client(tmp_path, call_cap=40, provider=provider) as (client, app):
        project = (await upload(client)).json()['workspace']['projectId']
        started = await client.post('/v2/projects/' + project + '/import',
            json={'kind': 'start', 'clientRequestId': 'import-1', 'allowTextRewrite': True, 'lite': True})
        assert started.status_code == 202, started.text
        runner = app.state.projects.imports.runners.get(started.json()['id'])
        if runner is not None:
            await runner
        [task] = [value for value in (await client.get('/v2/projects/' + project + '/tasks')).json()['tasks']
                  if value['id'] == started.json()['id']]
        assert (task['state'], task['error']) == ('succeeded', None), task
        operation = operation_of(app, project)
        policy = operation.capture.policy
        # A lite import never rewrites, has no map of the product's own and answers its tasks one by one.
        assert (policy.lite, policy.source_map, policy.concurrency, operation.capture.allow_text_rewrite) == (True, False, 1, False)
        app.state.intake.validate(operation, saved(app, project))
        # The scheme asked for its map twice and was refused; no task of the pipeline reached the provider, and the
        # block shows its source lines.
        assert [call['kind'] for call in provider.calls] == ['lite', 'lite']
        assert operation.attempts and any(issue.code == 'IMPORT_SOURCE_FALLBACK' for issue in operation.issues)
