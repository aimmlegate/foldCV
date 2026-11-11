"""T0.1 with R1: one diagnostics file per import with each call's usage and the coordinator's timing."""

import asyncio
from dataclasses import replace
import json
import os
import re
from types import SimpleNamespace

import pytest

from packages.resume_core.import_failure import TemplateImportFailure
from resume_api import import_usage
from resume_api.import_usage import ImportUsage
from resume_api.importer.template_transport import JOB_PERMIT
from resume_api.inference_admission import INFERENCE
from resume_api.providers.claude.content import ClaudeCliProvider, FixtureTransport
from resume_api.providers.content import ContentFailure, ReportedUsage
from resume_api.rewrite_timing import add_phase
from tests.providers.claude_relay import RelayTransport, stand_in
from tests.templates.pipeline_fixtures import NOW
from tests.templates.template_runtime_fixtures import RuntimeFixture
from tests.templates.test_semantic_admission import raw_proposal

PHASES = {'poolWait', 'preflight', 'cliStartup', 'modelTurn', 'cliProcess', 'decode'}
# Ids, codes, model names and ISO times: résumé text, prompts and replies have spaces or other letters.
PLAIN = re.compile(r'[A-Za-z0-9_.:+-]{1,128}')
WINDOWS = {'fiveHour': {'utilization': 0.25, 'resetsAt': 1800000000}, 'sevenDay': {'utilization': 0.05, 'resetsAt': 1800500000}}
DETAILS = {'claude': {'claude': {'uncachedInput': 2, 'cacheWrite5m': 0, 'cacheWrite1h': 8, 'cacheRead': 0, 'output': 4,
                                 'thinking': 1, 'costUsd': 0.002, 'numTurns': 2, 'assistantMessages': 1, **WINDOWS}},
           'codex': {'codex': {'input': 10, 'cachedInput': 0, 'output': 4, 'reasoningOutput': 2}}}


class Reporting:
    """The controlled transport as a CLI provider reports a call: its own numbers ride on the usage, its phases go
    through rewrite_timing; each call first reads the file as the import left it so far."""

    def __init__(self, fixture, detail):
        self.inner, self.detail, self.fixture, self.seen = fixture.transport, detail, fixture, []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def generate(self, request, cancel):
        files = list(usage_folder(self.fixture).glob('*.json'))
        self.seen.append(json.loads(files[0].read_text()) if files else None)
        for phase in ('preflight', 'cli_startup', 'model_turn', 'cli_process', 'account_queue'):
            add_phase(phase, 0.25)

        def returned(frame):
            request.on_return(replace(frame, usage=replace(frame.usage, detail=self.detail)))
        result = self.inner.generate(replace(request, on_return=returned), cancel)
        add_phase('decode', 0.25)
        return result


def usage_folder(fixture):
    return fixture.root / 'store' / 'diagnostics' / 'import-usage'


def stored(fixture):
    [path] = usage_folder(fixture).glob('*.json')
    return path, json.loads(path.read_text())


def strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, str):
        yield value


def assert_no_text(fixture, raw, record, prompts):
    data = json.loads(raw)
    assert all(PLAIN.fullmatch(text) for text in strings(data))
    lines = [line.strip() for unit in fixture.source.units for line in unit.text.splitlines() if len(line.strip()) >= 12]
    texts = [*lines, *[attempt.raw_return for attempt in record.attempts if attempt.raw_return], *prompts,
             fixture.source.original_name]
    assert lines and not any(text in raw for text in texts)


def assert_rows_follow_the_record(data, record):
    tasks = {task.id: task for task in record.tasks}
    assert [row['attemptId'] for row in data['attempts']] == [attempt.id for attempt in record.attempts]
    for row, attempt in zip(data['attempts'], record.attempts):
        assert (row['taskId'], row['blockId'], row['entry'], row['slot']) == (
            attempt.task_id, tasks[attempt.task_id].block_id, False, attempt.slot)
        assert (row['provider'], row['model'], row['effort']) == (
            attempt.model.adapter, attempt.model.model, attempt.model.effort)
        assert (row['outcome'], row['errorCode'], row['dispatchedAt'], row['returnedAt']) == (
            attempt.outcome, attempt.error_code, attempt.dispatched_at, attempt.returned_at)
        assert row['reported'] == attempt.usage.model_dump(by_alias=True, exclude={'complete'})


def assert_timing(data):
    for row in data['attempts']:
        assert set(row['phases']) == PHASES and all(value >= 0 for value in row['phases'].values())
    assert {'taskInput', 'reserve', 'dispatch', 'return', 'parse', 'review', 'finish'} <= set(data['steps'])
    for sums in data['steps'].values():
        assert sums['count'] >= 1 and set(sums) == {'count', 'lockWait', 'poolWait', 'transition', 'validation', 'write'}
        assert all(value >= 0 for value in sums.values())
    assert set(data['tasks']) == {'taskInput', 'derive', 'makeReviewInput', 'parseProposal'}
    assert all(value >= 0 for value in data['tasks'].values())
    # The parts this import runs are measured, not placeholders.
    assert all(data['tasks'][part] > 0 for part in ('taskInput', 'makeReviewInput', 'parseProposal'))
    assert {'view', 'guard', 'assemble', 'candidate', 'prepare', 'publish', 'publishedRead', 'workspaceHash',
            'record'} == set(data['finalization']) and all(value >= 0 for value in data['finalization'].values())
    assert data['finalization']['assemble'] > 0 and data['finalization']['record'] > 0


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['claude', 'codex'])
async def test_each_call_has_a_row_with_the_record_usage_its_provider_numbers_and_timing(tmp_path, provider):
    fixture = RuntimeFixture(tmp_path)
    fixture.transport = Reporting(fixture, DETAILS[provider])
    fixture.pipeline = fixture.fresh_pipeline()
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published'
    path, data = stored(fixture)
    record = fixture.current().project.template_operations[0]
    assert path.name == record.id + '.json' and len(record.attempts) == 2
    assert (data['version'], data['operationId'], data['projectId']) == (1, record.id, fixture.project)
    assert (data['startedAt'], data['endedAt'], data['state']) == (NOW, NOW, 'published')
    assert_rows_follow_the_record(data, record)
    other = 'codex' if provider == 'claude' else 'claude'
    for row in data['attempts']:
        assert row[provider] == DETAILS[provider][provider] and row[other] is None
        assert {name: row['phases'][name] for name in PHASES - {'poolWait'}} == dict.fromkeys(PHASES - {'poolWait'}, 0.25)
    assert_timing(data)
    # The file is rewritten as the import runs: the review saw the first call's row, before the import ended.
    first, second = fixture.transport.seen
    assert first is None and [row['attemptId'] for row in second['attempts']] == [record.attempts[0].id]
    assert (second['endedAt'], second['state'], second['attempts'][0]['outcome']) == (None, 'processing', 'completed')
    assert_no_text(fixture, path.read_text(), record, fixture.transport.prompts)


def satisfied(fixture):
    def script(_request, value):
        if 'targets' not in value:
            return raw_proposal(fixture.source)
        return {'results': [{'ruleId': target['ruleId'], 'targetId': target['targetId'], 'disposition': 'satisfied',
            'reason': '', 'evidence': [], 'actionable': False} for target in value['targets']]}
    return script


@pytest.mark.asyncio
@pytest.mark.parametrize('detail', ['valid', 'malformed'])
async def test_the_claude_cli_numbers_and_phases_reach_the_file_and_a_bad_field_changes_nothing(tmp_path, detail):
    directory, operations = tmp_path / 'claude stand-in', tmp_path / 'operations'
    cli = stand_in(directory)
    (directory / 'fixture.json').write_text(json.dumps({'case': 'relay', 'value': {}, 'detail': detail}))
    operations.mkdir(mode=0o700)
    fixture = RuntimeFixture(tmp_path / 'import')
    fixture.transport = RelayTransport(ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli)), operations,
                                       satisfied(fixture), directory / 'answers')
    fixture.pipeline = fixture.fresh_pipeline()
    permit = await INFERENCE.reserve(asyncio.Event())
    token = JOB_PERMIT.set(permit)
    try:
        result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    finally:
        JOB_PERMIT.reset(token)
        permit.release()
    assert result.state == 'published' and not result.issues
    record = fixture.current().project.template_operations[0]
    path, data = stored(fixture)
    assert_rows_follow_the_record(data, record)
    # The record keeps the CLI's counts whatever the cost fields: 12 uncached, 3 written and 5 read input tokens.
    assert [row['reported'] for row in data['attempts']] == [{'inputTokens': 20, 'cachedInputTokens': 5,
                                                             'outputTokens': 7}] * 2
    kept = {'uncachedInput': 12, 'cacheRead': 5, 'output': 7, 'assistantMessages': 1}
    full = {**kept, 'cacheWrite5m': 0, 'cacheWrite1h': 3, 'thinking': 2, 'costUsd': 0.01, 'numTurns': 2, **WINDOWS}
    for row in data['attempts']:
        assert row['claude'] == (full if detail == 'valid' else kept) and row['codex'] is None
        assert row['phases']['cliProcess'] > 0 and row['phases']['cliStartup'] > 0
    assert data['attempts'][0]['phases']['preflight'] > 0
    assert_timing(data)
    prompts = [(directory / name).read_text() for name in ('prompt-1.txt', 'prompt-2.txt')]
    assert_no_text(fixture, path.read_text(), record, prompts)


@pytest.mark.asyncio
async def test_a_failed_call_still_has_its_row_with_the_numbers_it_reported(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    detail = {'claude': {'uncachedInput': 7, 'costUsd': 0.003, 'assistantMessages': 0,
                         'fiveHour': {'utilization': 0.5, 'resetsAt': 9}}}

    def limited(_request, _cancel):
        raise ContentFailure('RATE_LIMITED', logical_attempts=1, usage=ReportedUsage(7, 0, 0, True, detail),
            cleanup_verified=True, dispatch_witness={'transport': 'controlled'})
    fixture.transport.generate = limited
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert result.state == 'published' and result.task_results[0].disposition == 'source_fallback'
    _path, data = stored(fixture)
    [row] = data['attempts']
    assert (row['outcome'], row['errorCode']) == ('transport_failure', 'RATE_LIMITED')
    assert row['reported'] == {'inputTokens': 7, 'cachedInputTokens': 0, 'outputTokens': 0}
    assert row['claude'] == detail['claude'] and set(row['phases']) == PHASES


@pytest.mark.asyncio
async def test_an_import_stopped_by_the_account_still_writes_its_end(tmp_path):
    fixture = RuntimeFixture(tmp_path)

    def exhausted(_request, _cancel):
        raise ContentFailure('QUOTA_EXHAUSTED', logical_attempts=1, usage=ReportedUsage(), cleanup_verified=True,
            dispatch_witness={'transport': 'controlled'})
    fixture.transport.generate = exhausted
    with pytest.raises(TemplateImportFailure, match='QUOTA_EXHAUSTED'):
        await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    _path, data = stored(fixture)
    assert (data['endedAt'], data['state']) == (NOW, 'processing')
    assert [(row['errorCode'], row['reported']['inputTokens'], row['claude']) for row in data['attempts']] == [
        ('QUOTA_EXHAUSTED', None, None)]


@pytest.mark.asyncio
async def test_a_failed_write_changes_nothing_in_the_import(tmp_path, monkeypatch):
    plain = RuntimeFixture(tmp_path / 'plain')
    expected = await plain.pipeline.run(plain.project, plain.command, admitted=plain.admitted)
    writes = []

    def broken(*_args, **_kwargs):
        writes.append(1)
        raise OSError('synthetic full disk')
    monkeypatch.setattr(import_usage, 'atomic_write', broken)
    fixture = RuntimeFixture(tmp_path / 'broken')
    result = await fixture.pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert writes and not list(usage_folder(fixture).glob('*.json'))
    assert (result.state, result.publication.state) == (expected.state, expected.publication.state)
    assert ([(attempt.slot, attempt.outcome, attempt.error_code, attempt.usage) for attempt in result.attempts]
            == [(attempt.slot, attempt.outcome, attempt.error_code, attempt.usage) for attempt in expected.attempts])
    assert fixture.text() == plain.text()


def operation(count, length):
    """A record-shaped operation with `count` attempts whose ids are `length` characters long."""
    model = SimpleNamespace(adapter='claude_cli', model='claude-opus-5-5', effort='high')
    usage = SimpleNamespace(input_tokens=18000, cached_input_tokens=0, output_tokens=900)
    attempts = [SimpleNamespace(id=f'attempt-{index:05d}'.ljust(length, 'x'), task_id='task-1', slot='initial',
        model=model, outcome='completed', error_code=None, dispatched_at=NOW, returned_at=NOW, usage=usage)
        for index in range(count)]
    return SimpleNamespace(state='published', tasks=[SimpleNamespace(id='task-1', block_id='projects', entry=None)],
        attempts=attempts)


def test_the_file_stays_within_its_bound_and_counts_the_oldest_rows_it_left_out(tmp_path):
    usage = ImportUsage(tmp_path, 'project-1', 'operation-1', NOW)
    record = operation(1500, 120)
    usage.observe(record)
    usage.save()
    raw = usage.path.read_bytes()
    data = json.loads(raw)
    assert len(raw) <= 256 * 1024 and data['droppedAttempts'] > 0
    assert [row['attemptId'] for row in data['attempts']] == [attempt.id for attempt in record.attempts[data['droppedAttempts']:]]


def test_the_forty_first_file_removes_the_oldest(tmp_path):
    folder = tmp_path / 'diagnostics' / 'import-usage'
    folder.mkdir(parents=True, mode=0o700)
    for index in range(40):
        path = folder / f'operation-{index:02d}.json'
        path.write_text('{}')
        os.utime(path, ns=(10 ** 18 + index * 10 ** 9,) * 2)
    (folder / 'notes.txt').write_text('kept')
    usage = ImportUsage(tmp_path, 'project-1', 'operation-new', NOW)
    usage.observe(operation(1, 20))
    usage.save()
    names = {path.name for path in folder.glob('*.json')}
    assert len(names) == 40 and 'operation-00.json' not in names and {'operation-01.json', 'operation-new.json'} <= names
    assert (folder / 'notes.txt').read_text() == 'kept'
    # Rewriting the same import's file removes nothing more.
    usage.save()
    assert {path.name for path in folder.glob('*.json')} == names


@pytest.mark.asyncio
async def test_the_last_write_stamps_the_end_when_the_record_cannot_be_read(tmp_path):
    def unreadable():
        raise RuntimeError('synthetic store failure')
    record = operation(1, 20)
    async with import_usage.collecting(tmp_path, 'project-1', 'operation-1', lambda: NOW, unreadable) as usage:
        usage.returned(record.attempts[0].id, None, record)
    data = json.loads(usage.path.read_text())
    assert (data['startedAt'], data['endedAt'], data['state']) == (NOW, NOW, 'published')
    assert [row['attemptId'] for row in data['attempts']] == [record.attempts[0].id]
