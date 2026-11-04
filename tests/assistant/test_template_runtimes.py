"""RuntimeInput.base_instructions (D141) is what Codex gets as baseInstructions and Claude as its system prompt."""

import threading

import pytest

from resume_api.agent.runtime import BASE_INSTRUCTIONS, DEVELOPER_INSTRUCTIONS, NativeSession, RuntimeInput
from resume_api.assistant.template_tools import TEMPLATE_BASE_INSTRUCTIONS, TEMPLATE_DEVELOPER_INSTRUCTIONS
from tests.assistant.test_claude_runtime import run
from tests.support.appserver import complete_events, input_value, runtime, script


def test_the_default_base_instructions_are_the_resume_ones():
    value = RuntimeInput(model='m', prompt='p', url='u', token='t', tools=(), allow_web=False)
    assert (value.base_instructions, value.developer_instructions) == (BASE_INSTRUCTIONS, DEVELOPER_INSTRUCTIONS)


@pytest.mark.asyncio
@pytest.mark.parametrize('instructions', [None, TEMPLATE_BASE_INSTRUCTIONS])
async def test_codex_starts_its_thread_with_the_runs_base_instructions(tmp_path, monkeypatch, instructions):
    requests, original = [], NativeSession.request

    def observed(session, method, params):
        requests.append((method, params))
        return original(session, method, params)
    monkeypatch.setattr(NativeSession, 'request', observed)
    value = input_value(**({'base_instructions': instructions} if instructions else {}))
    result = await runtime(tmp_path, value, script(value, turn_events=complete_events())).run(
        value, threading.Event(), lambda *_: None)
    assert result.state == 'completed'
    started = next(params for method, params in requests if method == 'thread/start')
    assert started['baseInstructions'] == (instructions or BASE_INSTRUCTIONS)


@pytest.mark.asyncio
async def test_claude_gets_the_runs_base_instructions_as_its_system_prompt(tmp_path):
    result, _events, calls, _listener, _audit, _directory = await run(tmp_path, 'complete',
        base_instructions=TEMPLATE_BASE_INSTRUCTIONS, developer_instructions=TEMPLATE_DEVELOPER_INSTRUCTIONS)
    args = calls[0]['args']
    assert result.state == 'completed'
    assert args[args.index('--system-prompt') + 1] == TEMPLATE_BASE_INSTRUCTIONS + '\n\n' + TEMPLATE_DEVELOPER_INSTRUCTIONS
    assert BASE_INSTRUCTIONS not in args[args.index('--system-prompt') + 1]
