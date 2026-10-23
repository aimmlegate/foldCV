"""Proof tools cannot expose credentials or dispatch outside their explicit allowance."""

import json
import os
import stat

import pytest

from packages.resume_core.agent_store import AgentFailure
from resume_api.agent.runtime import NativeSession
from resume_api.providers.codex_cli import CodexCliProvider
from resume_api.providers.content import ContentFailure
from tools.ct05_live_import import Allowance, guard_dispatch
from tools.ct05_v7_serve import write_json


def test_exhausted_allowance_and_assistant_turns_cannot_dispatch(tmp_path, monkeypatch):
    ledger = tmp_path / 'ledger.json'
    ledger.write_text(json.dumps({'cap': 1, 'spent': 1, 'attempts': []}))
    calls = []
    monkeypatch.setattr(CodexCliProvider, '_run', lambda *args, **kwargs: calls.append('exec'))
    monkeypatch.setattr(NativeSession, 'request', lambda *args, **kwargs: calls.append('assistant'))
    guard_dispatch(Allowance(ledger, 'synthetic'), tmp_path)
    with pytest.raises(ContentFailure, match='LIVE_ALLOWANCE_SPENT'):
        CodexCliProvider._run(object(), None, ['exec', '--model', 'synthetic'], None, None)
    with pytest.raises(AgentFailure, match='AGENT_RUNTIME_UNSUPPORTED'):
        NativeSession.request(object(), 'turn/start', {})
    assert calls == [] and json.loads(ledger.read_text())['spent'] == 1
    assert NativeSession.request(object(), 'model/list', {}) is None
    assert calls == ['assistant']


@pytest.mark.parametrize('failed', [False, True])
def test_last_allowed_exec_is_charged_before_dispatch_even_when_it_fails(tmp_path, monkeypatch, failed):
    ledger = tmp_path / 'ledger.json'
    ledger.write_text(json.dumps({'cap': 1, 'spent': 0, 'attempts': []}))
    observed, assistant_calls = [], []
    def dispatch(*args, **kwargs):
        state = json.loads(ledger.read_text())
        observed.append((state['spent'], state['attempts'][0]['status']))
        if failed:
            raise ContentFailure('PROCESS_FAILED')
        return b'synthetic result', b''
    monkeypatch.setattr(CodexCliProvider, '_run', dispatch)
    monkeypatch.setattr(NativeSession, 'request', lambda *args, **kwargs: assistant_calls.append('turn'))
    guard_dispatch(Allowance(ledger, 'synthetic'), tmp_path)
    with pytest.raises(AgentFailure, match='AGENT_RUNTIME_UNSUPPORTED'):
        NativeSession.request(object(), 'turn/start', {})
    assert assistant_calls == [] and json.loads(ledger.read_text())['spent'] == 0
    args = object(), None, ['exec', '--model', 'synthetic'], None, None
    if failed:
        with pytest.raises(ContentFailure, match='PROCESS_FAILED'):
            CodexCliProvider._run(*args)
    else:
        assert CodexCliProvider._run(*args) == (b'synthetic result', b'')
        assert (tmp_path / 'CT-01.stdout').read_bytes() == b'synthetic result'
    with pytest.raises(ContentFailure, match='LIVE_ALLOWANCE_SPENT'):
        CodexCliProvider._run(*args)
    state = json.loads(ledger.read_text())
    assert observed == [(1, 'dispatched')]
    assert state['spent'] == 1 and len(state['attempts']) == 1
    assert state['attempts'][0]['status'] == ('failed' if failed else 'completed')
    assert state['attempts'][0]['code'] == ('PROCESS_FAILED' if failed else None)


def test_launch_json_is_private_at_publication_under_permissive_umask(tmp_path, monkeypatch):
    import packages.resume_core.storage as storage
    original = os.replace
    seen = []
    def publish(source, target):
        seen.append((stat.S_IMODE(os.stat(source).st_mode), stat.S_IMODE(target.parent.stat().st_mode)))
        return original(source, target)
    monkeypatch.setattr(storage.os, 'replace', publish)
    mask = os.umask(0o022)
    try:
        path = tmp_path / 'proof' / 'launch.json'
        write_json(path, {'secret': 'synthetic-only'})
    finally:
        os.umask(mask)
    assert seen == [(0o600, 0o700)]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
