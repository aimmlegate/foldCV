"""Final native allowance accounting is exercised only with a copied ledger."""

import json
import asyncio

import pytest

from packages.resume_core.background_store import BackgroundFailure
from spikes.background.native_serial import spend
from spikes.background.native_serial import SerialProof
from spikes.background.native_serial import protocol_diagnostics


@pytest.mark.parametrize("fault", ["unauthorized", "exhausted", "count-mismatch", "auth", "quota", "duplicate"])
def test_final_native_dispatch_refuses_an_invalid_or_spent_allowance_before_launch(tmp_path, fault):
    attempt = dict(id="NB07a-1", pool="NB07a", variant="NB-X03:v01", status="failed", error=None)
    ledger = dict(pools={"NB07a": dict(authorized=True, cap=2, spent=0)}, attempts=[])
    if fault == "unauthorized": ledger["pools"]["NB07a"]["authorized"] = False
    elif fault == "exhausted": ledger["pools"]["NB07a"]["cap"] = 0
    elif fault == "count-mismatch": ledger["pools"]["NB07a"]["spent"] = 1
    else:
        ledger["attempts"].append(attempt)
        ledger["pools"]["NB07a"]["spent"] = 1
        if fault in {"auth", "quota"}: attempt["error"] = "AGENT_AUTH_REQUIRED" if fault == "auth" else "AGENT_QUOTA"
    path = tmp_path / "ledger.json"; path.write_text(json.dumps(ledger))
    before = path.read_bytes()
    with pytest.raises(BackgroundFailure):
        spend(path, variant="NB-X03:v01", job="synthetic-job", project="synthetic-project", hashes={"test": "a" * 64})
    assert path.read_bytes() == before


def test_final_native_dispatch_counts_failed_starts_without_borrowing_another_pool(tmp_path):
    ledger = dict(pools={"NB07a": dict(authorized=True, cap=2, spent=0),
        "NB00": dict(authorized=True, cap=10, spent=0), "NB07b": dict(authorized=True, cap=6, spent=0)}, attempts=[])
    path = tmp_path / "ledger.json"; path.write_text(json.dumps(ledger))
    first = spend(path, variant="NB-X03:v01", job="synthetic-first", project="synthetic-project", hashes={"test": "a" * 64})
    value = json.loads(path.read_bytes()); value["attempts"][0]["status"] = "failed"
    path.write_text(json.dumps(value))
    second = spend(path, variant="NB-X03:v02", job="synthetic-second", project="synthetic-project", hashes={"test": "a" * 64})
    assert (first, second) == ("NB07a-1", "NB07a-2")
    with pytest.raises(BackgroundFailure):
        spend(path, variant="not-a-reserve", job="synthetic-third", project="synthetic-project", hashes={"test": "a" * 64})
    final = json.loads(path.read_bytes())
    assert final["pools"]["NB07a"]["spent"] == 2 and len(final["attempts"]) == 2
    assert final["pools"]["NB00"] == ledger["pools"]["NB00"] and final["pools"]["NB07b"] == ledger["pools"]["NB07b"]


@pytest.mark.asyncio
async def test_native_evidence_wraps_real_empty_string_and_model_tool_arguments_without_affecting_results(tmp_path):
    from packages.resume_core.models.agent import AgentQuery
    from packages.resume_core.background_supervisor import ExecutionOutcome
    from tests.recovery.test_background_agent import environment
    service, factory, workspace, request, _connection, _old = await environment(tmp_path / "service")
    request.request.allow_web = False
    proof = SerialProof.__new__(SerialProof)
    proof.root = tmp_path / "evidence"; proof.root.mkdir()
    proof.original_session, proof.sessions = service.tools.session, {}
    observed = []
    async def execute(control, _actor):
        session = proof.session(control)
        try:
            observed.append(await session.call("check_resume", None))
            observed.append(await session.call("read_public_page", "https://example.com/"))
            observed.append(await session.call("get_resume_context", AgentQuery(kind="document", ids=["narrative"])))
            return ExecutionOutcome(finished_at=service.supervisor.clock.now())
        finally:
            await session.close()
    factory.callbacks[request.request.client_request_id] = execute
    try:
        job, _ = await service.submit(workspace.project_id, request)
        await factory.actor(job)
        await asyncio.wait_for(service.supervisor.controls[job.id].task, 10)
        assert service.store.read(workspace.project_id, job.id).execution == "completed"
        assert observed[0].get("error") is None and observed[2].get("snapshot") is not None
        assert observed[1]["error"]["code"] == "AGENT_TOOL_DENIED"
        rows = [json.loads(line) for line in (proof.root / (job.id + "-tools.jsonl")).read_text().splitlines()]
        assert [row["arguments"] for row in rows[:2]] == [None, "https://example.com/"]
        assert rows[2]["arguments"]["kind"] == "document"
        assert [row["result"] for row in rows] == observed
        assert not service.admission.locked()
    finally:
        await service.shutdown(); factory.verify(); service.supervisor.clock.verify()


@pytest.mark.parametrize("fault", ["healthy", "notification", "provider", "malformed", "shape"])
def test_native_protocol_observer_preserves_parser_decisions_and_redacts_bounded_failure(tmp_path, fault):
    from packages.resume_core.agent_store import AgentFailure
    from resume_api.agent.runtime import NativeSession, RuntimeInput
    from resume_api.providers.content import ContentFailure
    import threading
    token = "synthetic-private-capability-0123456789"
    value = RuntimeInput("synthetic-model", "synthetic context", "http://127.0.0.1/", token, (), False)
    session = NativeSession(value, threading.Event(), lambda *_args: None, startup=15, active=180)
    original = NativeSession.accept
    params = dict(error=dict(message="Bearer hidden-bearer-value " + token + " " + "x" * 10000,
        refresh_token="hidden-refresh-value", code="synthetic_error"), willRetry=True)
    raw = json.dumps(dict(method="warning" if fault == "healthy" else "error" if fault == "provider" else "unknown/event", params=params)).encode()
    if fault == "malformed": raw = b"not-json"
    if fault == "shape":
        session.pending[1] = "thread/start"
        raw = b'{"id":1,"result":{"thread":{}}}'
    with protocol_diagnostics(tmp_path):
        if fault == "healthy":
            assert session.accept(raw) is None and not list(tmp_path.glob("protocol-failure-*.json"))
            assert json.loads((tmp_path / "protocol-last-frame.json").read_text())["method"] == "warning"
        else:
            expected = KeyError if fault == "shape" else ContentFailure if fault == "malformed" else AgentFailure
            code = None if fault == "shape" else "INVALID_RESULT" if fault == "malformed" else "AGENT_PROTOCOL"
            with pytest.raises(expected, match="id" if fault == "shape" else code):
                session.accept(raw)
            files = list(tmp_path.glob("protocol-failure-*.json"));assert len(files) == 1
            text = files[0].read_text();assert len(text.encode()) < 16384
            assert token not in text and "hidden-bearer-value" not in text and "hidden-refresh-value" not in text
            row = json.loads(text);assert row["code"] == code
            if fault == "shape": assert row["detail"] == "'id'"
            if fault == "provider": assert row["willRetry"] is True
            if fault == "notification": assert row["method"] == "unknown/event"
    assert NativeSession.accept is original


@pytest.mark.parametrize("mode", ["error", "eof"])
def test_native_protocol_observer_retains_process_failure_without_raw_stdout_or_credentials(tmp_path, monkeypatch, mode):
    from resume_api.cli.process_runner import ProcessRunner, ProcessExit
    failure = ProcessExit(b"private raw stdout", b'Bearer private-token refresh_token="private-refresh" useful failure')
    def fail(*_args, **_kwargs):
        if mode == "error": raise failure
        return failure.stdout, failure.stderr
    monkeypatch.setattr(ProcessRunner, "run", fail)
    with protocol_diagnostics(tmp_path):
        if mode == "error":
            with pytest.raises(ProcessExit) as raised:
                ProcessRunner.run(None, interactive=True)
            assert raised.value is failure
        else:
            assert ProcessRunner.run(None, interactive=True) == (failure.stdout, failure.stderr)
        text = (tmp_path / ("protocol-process-failure.json" if mode == "error" else "protocol-process-exit.json")).read_text()
        assert all(secret not in text for secret in ["private-token", "private-refresh", "private raw stdout"])
        assert "useful failure" in text
    assert ProcessRunner.run is fail


@pytest.mark.parametrize("fault", ["none", "authority-changed", "already-passed", "reserve-deferred"])
def test_native_failed_variant_retry_requires_the_exact_new_grant_and_keeps_deferred_capacity(tmp_path, fault):
    import hashlib
    grant = dict(authorized=True, capTotal=4, failedStartsCount=True, retryVariants={"NB-X03:v01":3})
    authority=tmp_path/"native-retry-authorization.json";authority.write_text(json.dumps(grant))
    attempt=dict(id="NB07a-1",pool="NB07a",variant="NB-X03:v01",status="failed",error="AGENT_PROTOCOL")
    ledger=dict(pools={"NB07a":dict(authorized=True,cap=4,spent=1,retryAuthority=authority.name,
        retryAuthoritySha256=hashlib.sha256(authority.read_bytes()).hexdigest())},attempts=[attempt])
    if fault == "authority-changed": authority.write_text(json.dumps({**grant,"authorized":False}))
    if fault == "already-passed": attempt["status"]="passed"
    if fault == "reserve-deferred":
        ledger["attempts"]=[{**attempt,"id":"NB07a-"+str(n)} for n in range(1,4)];ledger["pools"]["NB07a"]["spent"]=3
    path=tmp_path/"ledger.json";path.write_text(json.dumps(ledger));before=path.read_bytes()
    if fault == "none":
        assert spend(path,variant="NB-X03:v01",job="retry-job",project="synthetic-project",hashes={})=="NB07a-2"
        after=json.loads(path.read_bytes());assert after["attempts"][0]==attempt and after["pools"]["NB07a"]["spent"]==2
    else:
        with pytest.raises(BackgroundFailure):spend(path,variant="NB-X03:v01",job="retry-job",project="synthetic-project",hashes={})
        assert path.read_bytes()==before


@pytest.mark.parametrize("fault", ["valid", "null-metadata", "foreign-thread", "foreign-turn", "missing-thread", "missing-turn", "missing-metadata", "unknown", "request"])
def test_moderation_metadata_is_inert_and_cannot_cross_the_active_turn_or_grant_requests(fault):
    import threading
    from packages.resume_core.agent_store import AgentFailure
    from resume_api.agent.runtime import NativeSession, RuntimeInput
    events, revoked = [], []
    value = RuntimeInput("synthetic-model", "context", "http://127.0.0.1/", "synthetic-token", (), False,
        revoke=lambda: revoked.append(True))
    session = NativeSession(value, threading.Event(), lambda *event: events.append(event))
    session.thread, session.turn = "thread-one", "turn-one"
    params = dict(threadId=session.thread, turnId=session.turn, metadata={"opaque": [1, None, "not instructions"]})
    if fault == "null-metadata": params["metadata"] = None
    if fault == "foreign-thread": params["threadId"] = "another-thread"
    if fault == "foreign-turn": params["turnId"] = "another-turn"
    if fault.startswith("missing-"): params.pop({"missing-thread":"threadId", "missing-turn":"turnId", "missing-metadata":"metadata"}[fault])
    frame = dict(method="turn/unknownMetadata" if fault == "unknown" else "turn/moderationMetadata", params=params)
    if fault == "request": frame["id"] = 42
    before = vars(session.result).copy()
    if fault in {"valid", "null-metadata"}:
        assert session.accept(json.dumps(frame).encode()) is None
        assert vars(session.result) == before and not events and not revoked
    elif fault == "request":
        response = json.loads(session.accept(json.dumps(frame).encode()))
        assert response["id"] == 42 and response["error"]["code"] == -32601
        assert session.result.state == "failed" and session.result.error == "AGENT_PROTOCOL" and revoked == [True]
    else:
        with pytest.raises(AgentFailure, match="AGENT_PROTOCOL"):
            session.accept(json.dumps(frame).encode())
        assert vars(session.result) == before and not events

