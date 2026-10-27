"""A run's tool calls (assistant/tools): call and fetch budgets, exact result bytes and the real public fetcher."""

import json

import pytest

from packages.resume_core import agent_limits as limits
from resume_api.agent.web import PublicFetcher
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
