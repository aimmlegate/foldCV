"""A run's tool calls (assistant/tools): call and fetch budgets, exact result bytes and the real public fetcher."""

import json

import pytest

from packages.resume_core import agent_limits as limits
from packages.resume_core.models.agent import AgentWebSource
from packages.resume_core.models.template_render import TemplateRendererIdentity
from packages.resume_core.models.template_workspace import WorkspaceV7
from resume_api.agent.web import PublicFetcher
from tests.assistant.support import PROJECT, assistant_app, conversation, finish, papers, proposals, start
from tests.support.assistant_tools import Fetcher, tool_session


def reply(result):
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_fetch_and_call_budgets_are_exact_and_cumulative():
    fetcher = Fetcher()
    session = tool_session(allow_web=True, fetcher=fetcher)
    try:
        for _ in range(limits.PAGE_FETCHES):
            assert reply(await session.call("read_public_page", lambda: session.fetch("https://public.example")))["source"]["id"]
        over = reply(await session.call("read_public_page", lambda: session.fetch("https://public.example")))
        assert over == {"error": {"code": "AGENT_SOURCE_LIMIT"}} and len(fetcher.urls) == limits.PAGE_FETCHES
        while session.calls < limits.TOOL_CALLS:
            assert "error" not in reply(await session.call("check_resume", lambda: {"issues": []}))
        assert reply(await session.call("check_resume", lambda: {"issues": []}))["error"]["code"] == "AGENT_TOOL_LIMIT"
        session.control.cancel.set()
        assert reply(await session.call("check_resume", lambda: {"issues": []}))["error"]["code"] == "AGENT_CANCELLED"
    finally:
        await session.close()


class LimitFetcher(Fetcher):
    """A page at the serialized limit with the fetch's placeholder run id; control characters take six bytes each."""

    async def fetch(self, request, cancel):
        source = await super().fetch(request, cancel)
        room = limits.SOURCE_BYTES - len(source.model_dump_json(by_alias=True).encode()) + len(source.text.encode())
        return AgentWebSource.model_validate({**source.model_dump(mode='json', by_alias=True), 'text': '\x01' * (room // 6)
            + 'x' * (room % 6)})


@pytest.mark.asyncio
async def test_a_source_at_the_size_limit_stays_readable_after_the_run_id_is_bound():
    session = tool_session(allow_web=True, fetcher=LimitFetcher())
    session.control.run_id = 'run_' + 'a' * 24
    try:
        fetched = reply(await session.call("read_public_page", lambda: session.fetch("https://public.example")))
        saved = session.service.sources[0]
        assert fetched['source']['runId'] == saved.run_id == session.control.run_id and fetched['source']['truncated']
        assert len(saved.model_dump_json(by_alias=True).encode()) <= limits.SOURCE_BYTES
        assert AgentWebSource.model_validate_json(saved.model_dump_json(by_alias=True)).text == saved.text
        assert len(saved.text) > 10000
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_result_bytes_are_bounded_per_call_and_per_run_without_a_second_copy():
    session = tool_session()
    try:
        # A single JSON string field has twelve bytes of framing.
        exact = {"value": "x" * (limits.TOOL_BYTES - 12)}
        over = await session.call("check_resume", lambda: {"value": "x" * (limits.TOOL_BYTES - 11)})
        assert reply(over)["error"]["code"] == "AGENT_TOOL_LIMIT" and session.result_bytes == 0
        for _ in range(limits.TOOL_TOTAL_BYTES // limits.TOOL_BYTES):
            result = await session.call("check_resume", lambda: exact)
            assert len(result.content) == 1 and len(result.content[0].text.encode()) == limits.TOOL_BYTES
            assert result.structuredContent is None and not result.isError
        assert session.result_bytes == limits.TOOL_TOTAL_BYTES
        final = await session.call("check_resume", lambda: {"value": "x"})
        assert final.isError and reply(final)["error"]["code"] == "AGENT_TOOL_LIMIT"
        assert session.result_bytes == limits.TOOL_TOTAL_BYTES
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_read_public_page_through_the_real_fetcher_denies_a_private_address(tmp_path):
    session = tool_session(allow_web=True, fetcher=PublicFetcher(tmp_path / "operations"))
    try:
        result = await session.call("read_public_page", lambda: session.fetch("http://127.0.0.1/private"))
        assert reply(result) == {"error": {"code": "AGENT_SOURCE_DENIED"}}
    finally:
        await session.close()


def long_blocks(count=12):
    """The papers workspace with `count` more main blocks of Cyrillic text: one format over them previews ~130 KB."""
    workspace, sources = papers()
    data = workspace.model_dump(by_alias=True)
    blocks = data['project']['document']['regions'][2]['blocks']
    first = blocks[0]
    for index in range(count):
        blocks.append({**first, 'id': f'block-long-{index}', 'content': [{'type': 'text', 'text': 'Опыт ' * 600,
            'styles': {}, 'presentation': first['content'][0]['presentation']}]})
    return WorkspaceV7.model_validate(data), sources


def test_a_large_proposal_is_stored_once_and_reaches_the_model_as_a_compact_success(tmp_path):
    results = []

    async def steps(tools, _value, _cancel, _emit):
        ops = [{'op': 'format_block', 'blockId': f'block-long-{index}', 'alignment': 'right'} for index in range(12)]
        results.append(await tools.call('propose_changes', {'request': {'summary': 'Выровнять', 'ops': ops}}))
        return 'Готово.'
    with assistant_app(tmp_path, steps, [long_blocks()]) as (client, _app, _runtime):
        _run, events = finish(client, start(client, conversation(client)))
        stored = proposals(client)
    assert [item['id'] for item in stored] == [results[0]['proposalId']] and len(stored[0]['preview']) == 12
    assert len(json.dumps(results[0], ensure_ascii=False).encode()) < 1024
    assert [event['type'] for event in events].count('proposal.ready') == 1


def test_a_proposal_over_the_run_budget_is_refused_before_it_is_stored(tmp_path):
    results = []

    async def steps(tools, _value, _cancel, _emit):
        tools.session().result_bytes = limits.TOOL_TOTAL_BYTES - 16
        results.append(await tools.call('propose_changes', {'request': {'summary': 'Правка', 'ops': [
            {'op': 'replace_text', 'blockId': 'block-paper-a', 'find': 'Shared', 'replace': 'Common'}]}}))
        return 'Готово.'
    with assistant_app(tmp_path, steps) as (client, _app, _runtime):
        _run, events = finish(client, start(client, conversation(client)))
        assert proposals(client) == []
    assert results == [{'error': {'code': 'AGENT_TOOL_LIMIT'}}]
    assert 'proposal.ready' not in [event['type'] for event in events]


def test_an_export_whose_link_reply_cannot_fit_the_run_budget_is_refused_before_it_runs(tmp_path):
    results, rendered = [], []

    async def render(_request):
        rendered.append(True)
        return b'PK\x03\x04synthetic-assistant-export'

    async def steps(tools, _value, _cancel, _emit):
        tools.session().result_bytes = limits.TOOL_TOTAL_BYTES - 200
        results.append(await tools.call('export_document', {'format': 'docx'}))
        return 'Готово.'
    with assistant_app(tmp_path, steps) as (client, application, _runtime):
        exports = application.state.projects.exports
        exports._renderer = TemplateRendererIdentity(id='captured-docx', version='test', sha256='a' * 64)
        exports.render = render
        _run, events = finish(client, start(client, conversation(client)))
        assert application.state.projects.repository.read(PROJECT).project.exports == []
    assert results == [{'error': {'code': 'AGENT_TOOL_LIMIT'}}] and rendered == []
    assert 'file.ready' not in [event['type'] for event in events]
