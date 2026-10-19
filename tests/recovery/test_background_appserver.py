"""Pinned protocol declarations are necessary, never sufficient for native go."""

import copy
import asyncio
import json

import pytest

from spikes.background.appserver_schema import ProtocolUnsupported, load_pinned, require_capabilities
from spikes.background.appserver_protocol import MultiplexProtocol, ProtocolLimits, TransportFailure


def wire(router, **value):
    return router.accept(json.dumps(value, ensure_ascii=False).encode())


def start(router, job, *, acknowledge=True):
    slot = router.register(job, "foldcv_" + job, ["read", "prepare", "apply"])
    request = router.request("thread/start", {"ephemeral": True}, job=job)
    wire(router, id=request["id"], result={"thread": {"id": "thread_" + job}})
    request = router.request("turn/start", {"threadId": slot.thread, "input": [{"type": "text", "text": job + " private context"}]}, job=job)
    wire(router, method="turn/started", params={"threadId": slot.thread, "turn": {"id": "turn_" + job}})
    if acknowledge:
        wire(router, id=request["id"], result={"turn": {"id": slot.turn}})
    return slot, request


def tool_frame(slot, *, identifier=100, call="call_1", **changes):
    params = dict(threadId=slot.thread, turnId=slot.turn, namespace=slot.namespace,
        tool="read", callId=call, arguments={"context": slot.job})
    params.update(changes)
    return dict(id=identifier, method="item/tool/call", params=params)


def terminal(router, slot, status="completed"):
    return wire(router, method="turn/completed", params={"threadId": slot.thread, "turn": {"id": slot.turn, "status": status}})


def delta(router, slot, value):
    return wire(router, method="item/agentMessage/delta", params={"threadId": slot.thread, "turnId": slot.turn, "delta": value})


def clean(slot):
    slot.tools_closed = slot.parser_closed = slot.operation_removed = True


@pytest.mark.parametrize("fault", ["none", "experimental", "dynamic-tools", "namespace", "input-schema",
    "output-schema", "interrupt-turn", "tool-turn", "tool-call", "reply-success"])
def test_pinned_schema_requires_routed_tools_structured_turns_and_targeted_interrupt(fault):
    schemas = copy.deepcopy(load_pinned())
    if fault == "experimental": del schemas["initialize"]["definitions"]["InitializeCapabilities"]["properties"]["experimentalApi"]
    elif fault == "dynamic-tools": del schemas["thread"]["properties"]["dynamicTools"]
    elif fault == "namespace":
        schemas["thread"]["definitions"]["DynamicToolSpec"]["oneOf"] = [item
            for item in schemas["thread"]["definitions"]["DynamicToolSpec"]["oneOf"]
            if item["properties"]["type"]["enum"] != ["namespace"]]
    elif fault == "input-schema":
        function = next(item for item in schemas["thread"]["definitions"]["DynamicToolSpec"]["oneOf"]
            if item["properties"]["type"]["enum"] == ["function"])
        function["required"].remove("inputSchema")
    elif fault == "output-schema": del schemas["turn"]["properties"]["outputSchema"]
    elif fault == "interrupt-turn": schemas["interrupt"]["required"].remove("turnId")
    elif fault == "tool-turn": schemas["toolCall"]["required"].remove("turnId")
    elif fault == "tool-call": schemas["toolCall"]["properties"]["callId"]["type"] = "integer"
    elif fault == "reply-success": schemas["toolReply"]["required"].remove("success")
    if fault == "none":
        result = require_capabilities(schemas)
        assert result == {"declaredSupport": True, "effectiveIsolationProved": False, "nativeGo": False}
    else:
        with pytest.raises(ProtocolUnsupported):
            require_capabilities(schemas)


@pytest.mark.parametrize("fault", ["none", "negative", "bool", "float", "string", "overflow", "request", "response", "unknown-field"])
def test_notification_timestamp_never_changes_authority_or_elapsed_deadlines(fault):
    router = MultiplexProtocol(clock=lambda: 10.0)
    slot, _ = start(router, "A")
    frame = dict(method="item/agentMessage/delta", params={"threadId": slot.thread, "turnId": slot.turn, "delta": "A only"},
        emittedAtMs=1792212715222)
    if fault == "negative": frame["emittedAtMs"] = -1
    elif fault == "bool": frame["emittedAtMs"] = True
    elif fault == "float": frame["emittedAtMs"] = 1.5
    elif fault == "string": frame["emittedAtMs"] = "1792212715222"
    elif fault == "overflow": frame["emittedAtMs"] = 2**63
    elif fault == "request": frame = {**tool_frame(slot), "emittedAtMs": 1792212715222}
    elif fault == "response": frame = {"id": 1, "result": {}, "emittedAtMs": 1792212715222}
    elif fault == "unknown-field": frame["unrecognized"] = True
    if fault == "none":
        assert wire(router, **frame)[0].job == "A" and slot.text == "A only"
    else:
        with pytest.raises(TransportFailure, match="PROTOCOL"):
            wire(router, **frame)
        assert slot.text == ""
    assert slot.active_deadline == 190.0


@pytest.mark.parametrize("reverse", [False, True])
def test_interleaved_frames_preserve_exact_job_thread_turn_and_call_ownership(reverse):
    router = MultiplexProtocol()
    a, request_a = start(router, "A", acknowledge=False)
    b, _ = start(router, "B")
    pending = tool_frame(a)
    assert wire(router, **pending) == []
    events_b = wire(router, **tool_frame(b, identifier=101))
    assert events_b[0].kind == "tool" and events_b[0].job == "B"
    events_a = wire(router, id=request_a["id"], result={"turn": {"id": a.turn}})
    assert events_a[-1].kind == "tool" and events_a[-1].job == "A"
    for slot in ([b, a] if reverse else [a, b]):
        reply = router.finish_tool(slot.job, slot.identity, "call_1", slot.job + " private result", success=True)
        assert reply["id"] == (100 if slot is a else 101)
        assert reply["result"]["contentItems"][0]["text"] == slot.job + " private result"
    assert wire(router, **pending)[0].value["result"]["contentItems"][0]["text"] == "A private result"
    assert len(a.calls) == len(b.calls) == 1
    assert delta(router, b, "B text")[0].job == "B"
    assert delta(router, a, "A text")[0].job == "A"
    assert (a.text, b.text) == ("A text", "B text")


@pytest.mark.parametrize("fault", ["namespace", "tool", "thread", "turn", "duplicate-call", "cancelled", "terminal", "old-identity", "global-rpc-id"])
def test_unknown_stale_and_foreign_tool_requests_cannot_gain_authority(fault):
    router = MultiplexProtocol()
    a, _ = start(router, "A")
    b, _ = start(router, "B")
    frame = tool_frame(a)
    if fault == "namespace": frame["params"]["namespace"] = b.namespace
    elif fault == "tool": frame["params"]["tool"] = "shell"
    elif fault == "thread": frame["params"]["threadId"] = "unknown-thread"
    elif fault == "turn": frame["params"]["turnId"] = b.turn
    elif fault == "duplicate-call":
        wire(router, **frame)
        frame["params"]["arguments"] = {"context": "foreign context"}
    elif fault == "cancelled": router.request("turn/interrupt", {"threadId": a.thread, "turnId": a.turn}, job="A")
    elif fault == "terminal": terminal(router, a)
    elif fault == "old-identity":
        wire(router, **frame)
        assert router.finish_tool("A", b.identity, "call_1", "foreign result", success=True) is None
        assert a.calls["call_1"].response is None
        return
    elif fault == "global-rpc-id":
        wire(router, **frame)
        with pytest.raises(TransportFailure, match="IDENTITY_INVALID"):
            wire(router, **tool_frame(b))
        assert not b.calls
        return
    result = wire(router, **frame)
    assert result[0].kind == "reply" and "error" in result[0].value
    assert not b.calls
    assert delta(router, b, "Still independent")[0].job == "B"


@pytest.mark.parametrize("finish_order", [("A", "B"), ("B", "A")])
def test_context_and_structured_output_never_cross_job_boundaries(finish_order):
    from pydantic import BaseModel, ValidationError
    from typing import Literal
    class ResultA(BaseModel):
        project: Literal["A"]
        text: str
    class ResultB(BaseModel):
        project: Literal["B"]
        text: str
    router = MultiplexProtocol()
    a, _ = start(router, "A")
    b, _ = start(router, "B")
    delta(router, a, '{"project":"A",')
    delta(router, b, '{"project":"B",')
    delta(router, b, '"text":"B private"}')
    delta(router, a, '"text":"A private"}')
    for name in finish_order:
        terminal(router, router.slots[name])
    assert ResultA.model_validate_json(a.text).text == "A private"
    assert ResultB.model_validate_json(b.text).text == "B private"
    with pytest.raises(ValidationError): ResultA.model_validate_json(b.text)
    with pytest.raises(ValidationError): ResultB.model_validate_json(a.text)


def test_targeted_interrupt_waits_for_turn_end_and_preserves_neighbor_progress():
    router = MultiplexProtocol()
    a, _ = start(router, "A")
    b, _ = start(router, "B")
    interrupt = router.request("turn/interrupt", {"threadId": a.thread, "turnId": a.turn}, job="A")
    wire(router, id=interrupt["id"], result={})
    clean(a)
    with pytest.raises(TransportFailure, match="CLEANUP_UNVERIFIED"):
        router.release("A", a.identity)
    assert wire(router, **tool_frame(a))[0].value["error"]
    assert delta(router, b, "Neighbor completed")[0].job == "B"
    terminal(router, a, "interrupted")
    released = router.release("A", a.identity)
    assert released.value == {"turnResourcesClosed": True, "sharedProcessDead": False}
    assert terminal(router, b)[0].value["status"] == "completed"


def test_shared_server_failure_fences_all_attached_turns_until_verified_death():
    router = MultiplexProtocol()
    a, _ = start(router, "A")
    b, _ = start(router, "B")
    assert {event.job for event in router.server_failed()} == {"A", "B"}
    with pytest.raises(TransportFailure, match="ACCOUNT_FENCED"):
        router.register("C", "foldcv_C", ["read"])
    for slot in (a, b):
        clean(slot)
        with pytest.raises(TransportFailure, match="CLEANUP_UNVERIFIED"):
            router.release(slot.job, slot.identity)
    router.verified_server_dead()
    for slot in (a, b):
        assert router.release(slot.job, slot.identity).value["sharedProcessDead"]
    assert not router.slots and not router.threads


@pytest.mark.parametrize("fault", ["text", "wire", "early", "tool-total", "frame", "duplicate-key", "nan", "deadline", "startup"])
def test_output_and_deadline_limits_release_only_verified_turn_resources(fault):
    if fault in {"deadline", "startup"}:
        now = [0.0]
        router = MultiplexProtocol(clock=lambda: now[0])
        if fault == "deadline":
            a, _ = start(router, "A")
            now[0] = 50.0
            b, _ = start(router, "B")
            now[0] = 180.0
            assert [(event.job, event.value) for event in router.expire()] == [("A", "DEADLINE")]
            request = router.request("turn/interrupt", {"threadId": a.thread, "turnId": a.turn}, job="A")
            wire(router, id=request["id"], result={})
            assert delta(router, b, "Neighbor continues")[0].job == "B"
            clean(a)
            with pytest.raises(TransportFailure, match="CLEANUP_UNVERIFIED"):
                router.release("A", a.identity)
        else:
            router.register("A", "foldcv_A", ["read"])
            router.request("thread/start", {"ephemeral": True}, job="A")
            now[0] = 15.0
            assert [(event.job, event.value) for event in router.expire()] == [("A", "STARTUP_TIMEOUT")]
        assert router.expire() == []
        return
    router = MultiplexProtocol(ProtocolLimits(text_bytes=8, wire_bytes_per_turn=2048, early_frames=1, tool_bytes=8))
    a, request = start(router, "A", acknowledge=fault != "early")
    b, _ = start(router, "B")
    if fault == "text": assert delta(router, a, "Overflow text")[0].value == "TEXT_LIMIT"
    elif fault == "wire":
        a.wire_bytes = router.limits.wire_bytes_per_turn
        assert delta(router, a, "a")[0].value == "WIRE_LIMIT"
    elif fault == "early":
        assert wire(router, **tool_frame(a)) == []
        with pytest.raises(TransportFailure, match="EARLY_FRAME_LIMIT"):
            wire(router, **tool_frame(a, identifier=102, call="call_2"))
    elif fault == "tool-total":
        wire(router, **tool_frame(a))
        with pytest.raises(TransportFailure, match="TOOL_LIMIT"):
            router.finish_tool("A", a.identity, "call_1", "too much content", success=True)
    elif fault == "frame":
        with pytest.raises(TransportFailure, match="FRAME_LIMIT"):
            router.accept(b"x" * (router.limits.frame_bytes + 1))
    else:
        raw = b'{"id":1,"id":2,"result":{}}' if fault == "duplicate-key" else b'{"id":NaN,"result":{}}'
        with pytest.raises(TransportFailure, match="PROTOCOL"):
            router.accept(raw)
    assert delta(router, b, "B ok")[0].job == "B"
    with pytest.raises(TransportFailure, match="CLEANUP_UNVERIFIED"):
        router.release("A", a.identity)


def test_retained_server_contexts_require_idle_rotation_instead_of_unbounded_threads():
    router = MultiplexProtocol(ProtocolLimits(threads_per_server=3))
    a, _ = start(router, "A")
    b, _ = start(router, "B")
    assert not router.needs_rotation() and router.needs_rotation(planned=2)
    for slot in (a, b):
        terminal(router, slot)
        clean(slot)
        router.release(slot.job, slot.identity)
    c, _ = start(router, "C")
    terminal(router, c)
    clean(c)
    router.release("C", c.identity)
    assert router.needs_rotation()
    with pytest.raises(TransportFailure, match="SERVER_ROTATION_REQUIRED"):
        router.register("D", "foldcv_D", ["read"])
    assert not router.slots


@pytest.mark.parametrize("fault", ["none", "duplicate", "changed-source", "cap", "count", "unauthorized",
    "unknown-pool", "variant", "next-group", "failed", "auth", "grant"])
def test_each_model_turn_spends_once_and_never_borrows_another_pool(tmp_path, fault):
    from spikes.background.native_turn_budget import AUTHORITY, NativeTurnDenied, spend_turn
    original = dict(pools={"NB00": dict(authorized=True, cap=10, spent=0),
        "NB07b": dict(authorized=True, cap=6, spent=0), "NB07a": dict(authorized=True, cap=14, spent=1)},
        attempts=[dict(id="old-serial", pool="NB07a", jobId="old-serial-job", status="passed", error=None)])
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(original))
    grant = tmp_path / "authority.json"
    grant.write_bytes(AUTHORITY.read_bytes())
    sources = {"frozen.py": "a" * 64}
    spend_turn(path, pool="NB00", variant="NB-R05:v01", job="A", source_hashes=sources, authority=grant)
    ledger = json.loads(path.read_bytes())
    variant, job, pool, current = "NB-R05:v01", "B", "NB00", sources
    if fault == "duplicate": job = "A"
    elif fault == "changed-source": current = {"frozen.py": "b" * 64}
    elif fault == "cap": ledger["pools"]["NB00"]["cap"] = 11
    elif fault == "count": ledger["pools"]["NB00"]["spent"] = 0
    elif fault == "unauthorized": ledger["pools"]["NB00"]["authorized"] = False
    elif fault == "unknown-pool": pool = "NB07a"
    elif fault == "variant": variant = "NB-X03:v03"
    elif fault == "next-group": variant = "NB-R05:v02"
    elif fault == "failed": ledger["attempts"][-1]["status"] = "failed"
    elif fault == "auth": ledger["attempts"][0]["error"] = "AUTH_REQUIRED"
    elif fault == "grant":
        value = json.loads(grant.read_bytes());value["authorized"] = False;grant.write_text(json.dumps(value))
    path.write_text(json.dumps(ledger));before = path.read_bytes()
    if fault != "none":
        with pytest.raises(NativeTurnDenied):
            spend_turn(path, pool=pool, variant=variant, job=job, source_hashes=current, authority=grant)
        assert path.read_bytes() == before
        return
    second = spend_turn(path, pool=pool, variant=variant, job=job, source_hashes=current, authority=grant)
    assert second["id"] == "NB00-2"
    ledger = json.loads(path.read_bytes())
    assert ledger["pools"]["NB07b"] == original["pools"]["NB07b"]
    assert ledger["pools"]["NB07a"] == original["pools"]["NB07a"]
    assert ledger["attempts"][0] == original["attempts"][0]
    for row in ledger["attempts"][1:]: row["status"] = "passed"
    path.write_text(json.dumps(ledger))
    third = spend_turn(path, pool="NB00", variant="NB-R05:v02", job="C", source_hashes=sources, authority=grant)
    assert third["id"] == "NB00-3"


@pytest.mark.asyncio
async def test_second_api_maintenance_and_login_cannot_take_a_live_server_profile(tmp_path):
    import threading
    import time
    from resume_api.inference_admission import AdmissionTimeout
    from resume_api.profile_ownership import native_profile
    class EmptyProfile:
        root = tmp_path
        def prepare(self):
            pass
    owner = EmptyProfile()
    cancel = threading.Event()
    peer = await pipe_peer(tmp_path).start()
    try:
        with native_profile(owner, cancel, deadline=time.monotonic() + 1):
            for index, action in enumerate(("second-api", "maintenance", "login")):
                with pytest.raises(AdmissionTimeout):
                    with native_profile(owner, cancel, deadline=time.monotonic() + 1, blocking=False):
                        pytest.fail("A live profile owner was bypassed: " + action)
                peer.send({"id": index, "method": "fixture/profile-lock",
                    "params": {"path": str(owner.root / ".foldcv-inference.lock")}})
                result = json.loads(await asyncio.wait_for(peer.receive(), 3))["result"]
                assert not result["acquired"] and result["pid"] != __import__("os").getpid()
            assert not cancel.is_set() and peer.process.poll() is None
    finally:
        await peer.close()
    with native_profile(owner, cancel, deadline=time.monotonic() + 1, blocking=False):
        assert not cancel.is_set()


@pytest.mark.asyncio
async def test_coordinator_death_with_a_live_child_cannot_advertise_a_free_profile(tmp_path):
    import os
    import threading
    import time
    from types import SimpleNamespace
    from resume_api.inference_admission import AdmissionBlocked
    from resume_api.lifecycle import reap_owned
    from resume_api.profile_ownership import SHARED, native_profile, recover_profile
    root = tmp_path / "profile"
    root.mkdir(mode=0o700)
    profile = SimpleNamespace(root=root, prepare=lambda: None)
    peer = await pipe_peer(tmp_path).start()
    try:
        peer.send({"id": 1, "method": "fixture/owner-and-orphan", "params": {
            "lockPath": str(root / ".foldcv-inference.lock"), "markerPath": str(root / SHARED),
            "operationsRoot": str(peer.files.root)}})
        result = json.loads(await asyncio.wait_for(peer.receive(), 3))["result"]
        assert result["ownerPid"] == peer.process.pid
        assert await asyncio.to_thread(peer.process.wait, timeout=3) == 0
        os.kill(result["childPid"], 0)
        assert reap_owned(peer.files.root) == 0 and recover_profile(profile, peer.files.root)
        for _action in ("second-api", "maintenance", "login"):
            with pytest.raises(AdmissionBlocked):
                with native_profile(profile, threading.Event(), deadline=time.monotonic() + 1, blocking=False):
                    pytest.fail("Orphaned server ownership was lost")
        os.kill(result["childPid"], 0)
    finally:
        witness = await peer.close()
    assert witness["ownedGroupCleanupVerified"] and witness["operationRemoved"]
    assert not recover_profile(profile, peer.files.root) and not (root / SHARED).exists()
    with native_profile(profile, threading.Event(), deadline=time.monotonic() + 1, blocking=False):
        pass


@pytest.mark.parametrize("fault", ["none", "pending", "neighbor-pending", "live-host", "bad-pid", "extra-field"])
def test_shared_profile_recovery_requires_complete_detached_host_ownership(tmp_path, fault):
    import os
    from types import SimpleNamespace
    from resume_api.profile_ownership import SharedOwnership, SHARED, recover_profile
    from resume_api.lifecycle import SpikeError
    profile_root, operations = tmp_path / "profile", tmp_path / "operations"
    profile_root.mkdir(mode=0o700)
    operations.mkdir(mode=0o700)
    (profile_root / ".foldcv-inference.lock").touch(mode=0o600)
    marker = profile_root / SHARED
    ownership = SharedOwnership(marker, operations)
    if fault in {"pending", "neighbor-pending"}:
        ownership.thread_pending()
        if fault == "neighbor-pending":
            ownership.thread_pending()
            ownership.thread_ready(())
    elif fault == "live-host":
        ownership.thread_pending()
        ownership.thread_ready((os.getpid(),))
        with pytest.raises(SpikeError, match="CLEANUP_FAILED"):
            ownership.generation_closed((os.getpid(),))
    elif fault in {"bad-pid", "extra-field"}:
        record = json.loads(marker.read_bytes())
        if fault == "bad-pid": record["hostPids"] = [2**63]
        else: record["unrecognized"] = True
        marker.write_text(json.dumps(record))
    assert recover_profile(SimpleNamespace(root=profile_root), operations) is (fault != "none")
    assert marker.exists() is (fault != "none")


@pytest.mark.parametrize("require_host,foreign", [(False, False), (True, False), (False, True)])
def test_tool_free_thread_allows_no_host_without_accepting_other_children(monkeypatch, require_host, foreign):
    from types import SimpleNamespace
    import subprocess
    from resume_api.agent.runtime import CodexAgentRuntime
    from packages.resume_core.agent_store import AgentFailure
    monkeypatch.setattr(subprocess, "check_output", lambda *_args, **_kwargs: "456 123 /foreign-child\n" if foreign else "")
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=b""))
    files = SimpleNamespace(process=SimpleNamespace(pid=123))
    if require_host or foreign:
        with pytest.raises(AgentFailure, match="AGENT_RUNTIME_UNSUPPORTED"):
            CodexAgentRuntime.check_owned_host(files, require_host=require_host)
    else:
        assert CodexAgentRuntime.check_owned_host(files, require_host=False) == ()


@pytest.mark.parametrize("fault", ["none", "pending", "pending-status", "missing", "wrong-cap", "rewritten-failure", "refunded", "proposal", "no-instruction", "failed-retry"])
def test_one_native_retry_requires_explicit_authority_and_retains_both_failed_starts(tmp_path, fault):
    import hashlib
    from pathlib import Path
    from spikes.background.native_turn_budget import spend_turn, NativeTurnDenied, ROLES
    handoff = Path("docs/gui/handoffs/BACKGROUND-WORK")
    original = json.loads((handoff / "nb00b-evidence/failed-native-pair.json").read_text())
    ledger = {"pools": {"NB00": dict(authorized=True, cap=12, spent=2),
        "NB07a": dict(cap=14, spent=10, dispatchClosed=True), "NB07b": dict(cap=6, spent=0)}, "attempts": original}
    authority = tmp_path / "authority.json"
    authority.write_bytes((handoff / "parallel-transport-authorization.json").read_bytes())
    proposal = tmp_path / "proposal.md"
    proposal.write_bytes((handoff / "nb07a-evidence/parallel-transport-proposal.md").read_bytes())
    retry = tmp_path / "retry.json"
    grant = json.loads((handoff / "native-feasibility-retry-authorization.json").read_text())
    grant.update(authorized=True, status="approved_by_user", userInstruction="Synthetic approval for a copied ledger only", approvedAt="2026-10-17T00:00:00+00:00")
    retry_proposal = tmp_path / "retry-proposal.md"
    retry_proposal.write_bytes((handoff / "nb00b-evidence/native-retry-proposal.md").read_bytes())
    if fault == "pending": grant["authorized"] = False
    elif fault == "pending-status": grant["status"] = "pending_user_approval"
    elif fault == "wrong-cap": ledger["pools"]["NB00"]["cap"] = 13
    elif fault == "rewritten-failure": ledger["attempts"][0]["status"] = "passed"
    elif fault == "refunded": ledger["pools"]["NB00"]["spent"] = 0
    elif fault == "proposal": retry_proposal.write_text("Changed proposal")
    elif fault == "no-instruction": grant["userInstruction"] = None
    retry.write_text(json.dumps(grant))
    if fault == "missing": retry.unlink()
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(ledger))
    before = path.read_bytes()
    options = dict(authority=authority, proposal=proposal, retry_authority=retry, retry_proposal=retry_proposal)
    def spend(variant, number):
        return spend_turn(path, pool="NB00", variant=variant, job="synthetic-retry-" + str(number),
            source_hashes={"fixed.py": "b" * 64}, **options)
    if fault not in {"none", "failed-retry"}:
        with pytest.raises(NativeTurnDenied): spend("NB-R05:v01", 3)
        assert path.read_bytes() == before
        return
    number = 2
    for variant, roles in ROLES.items():
        if not variant.startswith("NB-R05:"): continue
        for role in roles:
            number += 1
            row = spend(variant, number)
            assert row["id"] == "NB00-" + str(number) and row["role"] == role and row["historicalStarts"] == 2
            assert row["retryAuthoritySha256"] == hashlib.sha256(retry.read_bytes()).hexdigest()
            current = json.loads(path.read_bytes())
            current["attempts"][-1]["status"] = "failed" if fault == "failed-retry" else "passed"
            path.write_text(json.dumps(current))
            if fault == "failed-retry":
                with pytest.raises(NativeTurnDenied): spend(variant, number + 1)
                return
    current = json.loads(path.read_bytes())
    assert current["attempts"][:2] == json.loads((handoff / "nb00b-evidence/failed-native-pair.json").read_text())
    assert current["pools"]["NB00"]["spent"] == 12 and current["pools"]["NB07a"] == ledger["pools"]["NB07a"]
    assert current["pools"]["NB07b"] == ledger["pools"]["NB07b"]
    with pytest.raises(NativeTurnDenied): spend("NB-R05:v01", 13)


@pytest.mark.parametrize("fault", ["none", "shell", "plugins", "mcp", "history", "discovery", "web", "instructions", "ambient"])
def test_effective_configuration_rejects_native_tools_discovery_and_ambient_layers(fault):
    from pathlib import Path
    from spikes.background.appserver_offline import validate_config
    frames = json.loads(Path("docs/gui/handoffs/BACKGROUND-WORK/nb00b-evidence/effective-config-frames.json").read_bytes())
    result = copy.deepcopy(next(frame["result"] for frame in frames if frame.get("id") == 2))
    cfg = result["config"]
    if fault in {"shell", "plugins"}: cfg["features"]["shell_tool" if fault == "shell" else "plugins"] = True
    elif fault == "mcp": cfg["mcp_servers"] = {"foreign": {"url": "https://invalid.example"}}
    elif fault == "history": cfg["history"]["persistence"] = "save-all"
    elif fault == "discovery": cfg["features"]["skip_host_skill_discovery"] = False
    elif fault == "web": cfg["web_search"] = "live"
    elif fault == "instructions": cfg["developer_instructions"] = "ambient instructions"
    elif fault == "ambient": result["layers"].append({"name": {"type": "user"}, "config": {"model": "foreign"}})
    if fault == "none": assert validate_config(result) == cfg
    else:
        with pytest.raises(ValueError): validate_config(result)


def test_early_completion_never_dispatches_later_buffered_tools():
    router = MultiplexProtocol()
    a, request = start(router, "A", acknowledge=False)
    b, _ = start(router, "B")
    assert terminal(router, a) == []
    assert wire(router, **tool_frame(a)) == []
    actions = wire(router, id=request["id"], result={"turn": {"id": a.turn}})
    assert not any(action.kind == "tool" for action in actions)
    assert any(action.kind == "reply" and action.value.get("error") for action in actions)
    assert delta(router, b, "B stays active")[0].job == "B"


def test_registration_reserves_context_capacity_before_any_rpc_or_model_start():
    router = MultiplexProtocol(ProtocolLimits(threads_per_server=2))
    router.register("A", "foldcv_A", ["read"])
    router.register("B", "foldcv_B", ["read"])
    with pytest.raises(TransportFailure, match="SERVER_ROTATION_REQUIRED"):
        router.register("C", "foldcv_C", ["read"])
    assert set(router.slots) == {"A", "B"} and not router.pending


def test_callback_from_released_turn_cannot_complete_a_new_job_identity():
    router = MultiplexProtocol()
    a, _ = start(router, "A")
    wire(router, **tool_frame(a))
    assert router.finish_tool("A", a.identity, "call_1", "old result", success=True)
    terminal(router, a)
    clean(a)
    router.release("A", a.identity)
    replacement = router.register("A", "foldcv_new_A", ["read"])
    assert router.finish_tool("A", a.identity, "call_1", "late old result", success=True) is None
    assert not replacement.calls and replacement.text == ""


def pipe_peer(tmp_path, *, fixture=None, **limits):
    from contextlib import contextmanager
    from pathlib import Path
    import shutil
    import sys
    from spikes.background.appserver_wire import OwnedRpcPipe
    from spikes.background.harness import SYNTHETIC_SPAWN
    @contextmanager
    def launch(operation):
        target = operation / "fake_appserver.py"
        shutil.copyfile(Path("spikes/background/fake_appserver.py"), target)
        if fixture is not None:
            (operation / "fixture.json").write_text(json.dumps(fixture))
        args = ("-I", "-S", "-u", str(target))
        token = SYNTHETIC_SPAWN.set((sys.executable, *args))
        try:
            yield Path(sys.executable), args, {"HOME": str(operation), "LANG": "C.UTF-8"}
        finally:
            SYNTHETIC_SPAWN.reset(token)
    return OwnedRpcPipe(tmp_path / "operations", launch, **limits)


@pytest.mark.asyncio
async def test_owned_pipe_preserves_interleaved_large_frames_and_verifies_process_cleanup(tmp_path):
    peer = await pipe_peer(tmp_path).start()
    try:
        frames = [{"threadId": "B", "text": "B" * 10000}, {"threadId": "A", "text": "A" * 10000}]
        peer.send({"method": "fixture/emit", "params": {"frames": frames}})
        assert [json.loads(await asyncio.wait_for(peer.receive(), 3)) for _ in frames] == frames
    finally:
        result = await peer.close()
    assert result["ownedGroupCleanupVerified"] and result["operationRemoved"]
    assert peer.process.poll() is not None and await peer.close() == result


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["exit", "partial"])
async def test_pipe_exit_or_partial_frame_requires_owned_cleanup_before_release(tmp_path, mode):
    peer = await pipe_peer(tmp_path).start()
    try:
        peer.send({"method": "fixture/exit", "params": {"code": 7}} if mode == "exit"
            else {"method": "fixture/partial", "params": {"raw": '{"partial":'}})
        with pytest.raises(TransportFailure, match="SERVER_EXITED" if mode == "exit" else "INCOMPLETE_FRAME"):
            await asyncio.wait_for(peer.receive(), 3)
        assert not peer.cleanup_verified
    finally:
        result = await peer.close()
    assert result["ownedGroupCleanupVerified"] and result["operationRemoved"]


@pytest.mark.asyncio
async def test_pipe_queue_overflow_stops_reading_until_owned_shutdown(tmp_path):
    peer = await pipe_peer(tmp_path, queue_frames=1).start()
    try:
        peer.send({"method": "fixture/emit", "params": {"frames": [{"value": "A"}, {"value": "B"}]}})
        async def overflow():
            while peer.error is None:
                peer.changed.clear()
                if peer.error is None:
                    await peer.changed.wait()
        await asyncio.wait_for(overflow(), 3)
        assert len(peer.frames) == 1 and peer.frame_bytes <= peer.queue_bytes
        assert json.loads(await peer.receive()) == {"value": "A"}
        with pytest.raises(TransportFailure, match="FRAME_QUEUE_LIMIT"):
            await peer.receive()
        assert not peer.cleanup_verified
    finally:
        await peer.close()
    assert peer.cleanup_verified


@pytest.mark.parametrize("fault", ["none", "pending", "pending-status", "missing", "wrong-cap", "changed-history",
    "reclassified", "refunded", "proposal", "prior-authority", "no-instruction", "wrong-pool", "failed-retry"])
def test_publication_retry_requires_a_new_grant_and_preserves_all_six_charged_starts(tmp_path, fault):
    import hashlib
    from pathlib import Path
    from spikes.background.native_turn_budget import spend_turn, NativeTurnDenied, GROUPS
    handoff = Path("docs/gui/handoffs/BACKGROUND-WORK")
    historical = json.loads((handoff / "nb00b-evidence/first-six-native-starts.json").read_text())
    ledger = dict(pools={"NB00": dict(authorized=True, cap=16, spent=6),
        "NB07a": dict(authorized=True, cap=14, spent=10, dispatchClosed=True),
        "NB07b": dict(authorized=True, cap=6, spent=0)}, attempts=json.loads(json.dumps(historical)))
    options = {}
    for key, name in dict(authority="parallel-transport-authorization.json",
            proposal="nb07a-evidence/parallel-transport-proposal.md",
            retry_authority="native-feasibility-retry-authorization.json",
            repair_authority="native-feasibility-repair-authorization.json",
            repair_proposal="nb00b-evidence/publication-retry-proposal.md").items():
        path = tmp_path / (key + ".json")
        path.write_bytes((handoff / name).read_bytes())
        options[key] = path
    grant = json.loads(options["repair_authority"].read_bytes())
    grant.update(authorized=True, status="approved_by_user", userInstruction="Synthetic copied-ledger approval only",
        approvedAt="2026-10-17T00:00:00+00:00")
    if fault == "pending": grant["authorized"] = False
    elif fault == "pending-status": grant["status"] = "pending_user_approval"
    elif fault == "wrong-cap": ledger["pools"]["NB00"]["cap"] = 17
    elif fault == "changed-history": ledger["attempts"][3]["jobId"] = "changed-history"
    elif fault == "reclassified": ledger["attempts"][5]["status"] = "passed"
    elif fault == "refunded": ledger["pools"]["NB00"]["spent"] = 5
    elif fault == "proposal": options["repair_proposal"].write_text("Changed proposal")
    elif fault == "prior-authority": options["retry_authority"].write_text("Changed prior grant")
    elif fault == "no-instruction": grant["userInstruction"] = ""
    elif fault == "wrong-pool": grant["pool"] = "NB07b"
    options["repair_authority"].write_text(json.dumps(grant))
    if fault == "missing": options["repair_authority"].unlink()
    path = tmp_path / "attempts.json"
    path.write_text(json.dumps(ledger))
    before = path.read_bytes()
    sequence = [variant for variant, count in GROUPS["NB00"] for _ in range(count)]
    def spend(index):
        return spend_turn(path, pool="NB00", variant=sequence[index], job="synthetic-publication-retry-" + str(index),
            source_hashes={"source.py": "a" * 64}, **options)
    if fault not in {"none", "failed-retry"}:
        with pytest.raises(NativeTurnDenied):
            spend(0)
        assert path.read_bytes() == before
        return
    for index in range(10):
        row = spend(index)
        assert row["id"] == "NB00-" + str(index + 7) and row["historicalStarts"] == 6
        assert row["retryAuthority"] == str(options["repair_authority"])
        assert row["retryAuthoritySha256"] == hashlib.sha256(options["repair_authority"].read_bytes()).hexdigest()
        current = json.loads(path.read_bytes())
        assert current["attempts"][:6] == historical and current["pools"]["NB00"]["spent"] == index + 7
        assert all(current["pools"][key] == ledger["pools"][key] for key in ("NB07a", "NB07b"))
        current["attempts"][-1]["status"] = "failed" if fault == "failed-retry" else "passed"
        path.write_text(json.dumps(current))
        if fault == "failed-retry":
            before = path.read_bytes()
            with pytest.raises(NativeTurnDenied):
                spend(index + 1)
            assert path.read_bytes() == before
            break


def shared_peer(tmp_path, *, clock=None, interrupt_completes=True, limits=ProtocolLimits(), startup_frame=None):
    from contextlib import contextmanager
    from pathlib import Path
    from spikes.background.appserver_driver import SharedAppServer
    from resume_api.profile_ownership import shared_profile
    import threading
    import time
    frames = json.loads(Path("docs/gui/handoffs/BACKGROUND-WORK/nb00b-evidence/effective-config-frames.json").read_bytes())
    fixture = {"effectiveConfig": next(frame["result"] for frame in frames if frame.get("id") == 2),
        "interruptCompletes": interrupt_completes}
    if startup_frame is not None:
        fixture["startupFrame"] = startup_frame
    held = []
    class EmptyProfile:
        root = tmp_path / "empty-profile"
        def prepare(self):
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
    profile = EmptyProfile()
    @contextmanager
    def owner():
        held.append(True)
        try:
            with shared_profile(profile, threading.Event(), deadline=time.monotonic() + 1,
                    operations_root=tmp_path / "operations") as ownership:
                yield ownership
        finally:
            held.append(False)
    driver = SharedAppServer(tmp_path / "operations", lambda: pipe_peer(tmp_path, fixture=fixture, limits=limits),
        owner=owner, verify_host=lambda _pipe: (), clock=clock, limits=limits)
    driver.test_owner_events = held
    return driver


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["none", "remote-enabled", "unknown-field"])
async def test_shared_startup_accepts_timestamped_metadata_and_retains_first_failure(tmp_path, fault):
    frame = {"method": "remoteControl/status/changed", "params": {"status": "disabled"}, "emittedAtMs": 1792212715222}
    if fault == "remote-enabled": frame["params"]["status"] = "enabled"
    elif fault == "unknown-field": frame["unknown"] = True
    driver = shared_peer(tmp_path, startup_frame=frame)
    try:
        if fault == "none":
            await driver.prepare()
            assert driver.models == {"gpt-6-luna"} and not driver.fenced and not driver.live
        else:
            code = "ISOLATION_FAILED" if fault == "remote-enabled" else "PROTOCOL"
            with pytest.raises(TransportFailure, match=code):
                await driver.prepare()
            assert driver.fence_code == code and driver.fenced
            with pytest.raises(TransportFailure, match=code):
                await driver.rpc("config/read", {})
    finally:
        await driver.close()
    assert driver.owner_context is None and driver.pipe is None


def shared_input(job, *, tools=False, **changes):
    from spikes.background.appserver_driver import TurnInput
    async def call(_name, _arguments):
        return job + " private context", True
    async def close():
        return True
    return TurnInput(job, "gpt-6-luna", job + " captured context", "Use this job's captured tools only.",
        changes.pop("cancelled", asyncio.Event()), tools=({"name": "read", "description": "Read captured context",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},) if tools else (),
        call=changes.pop("call", call) if tools else None, close_tools=changes.pop("close_tools", close) if tools else None,
        **changes)


def emit_shared(driver, *frames):
    driver.pipe.send({"method": "fixture/emit", "params": {"frames": list(frames)}})


def complete_shared(driver, job, text, *, status="completed"):
    slot = driver.live[job].slot
    params = {"threadId": slot.thread, "turnId": slot.turn}
    item = {"id": "message_" + job, "type": "agentMessage", "phase": "final_answer", "text": text}
    emit_shared(driver, {"method": "item/started", "params": {**params, "item": {**item, "text": ""}}},
        {"method": "item/agentMessage/delta", "params": {**params, "itemId": item["id"], "delta": text}},
        {"method": "item/completed", "params": {**params, "item": item}},
        {"method": "turn/completed", "params": {"threadId": slot.thread, "turn": {"id": slot.turn, "status": status}}})


@pytest.mark.asyncio
@pytest.mark.parametrize("reverse", [False, True])
async def test_owned_shared_pipe_routes_interleaved_agent_and_structured_turns(tmp_path, reverse):
    driver = shared_peer(tmp_path)
    ready_a, ready_b, called, release = (asyncio.Event() for _ in range(4))
    calls = []
    async def call(name, arguments):
        calls.append((name, arguments))
        called.set()
        await release.wait()
        return "A private context", True
    a = asyncio.create_task(driver.run(shared_input("A", tools=True, call=call, started=ready_a.set)))
    b = asyncio.create_task(driver.run(shared_input("B", started=ready_b.set,
        output_schema={"type": "object", "properties": {"project": {"const": "B"}}, "required": ["project"], "additionalProperties": False})))
    try:
        await asyncio.wait_for(asyncio.gather(ready_a.wait(), ready_b.wait()), 5)
        slot_a, slot_b = driver.live["A"].slot, driver.live["B"].slot
        pid = driver.pipe.process.pid
        emit_shared(driver, tool_frame(slot_a, namespace=slot_b.namespace), tool_frame(slot_a, identifier=101))
        await asyncio.wait_for(called.wait(), 5)
        assert calls == [("read", {"context": "A"})] and len(slot_a.calls) == 1 and not slot_b.calls
        release.set()
        first, second = (("A", "B") if reverse else ("B", "A"))
        complete_shared(driver, first, "A done" if first == "A" else '{"project":"B"}')
        complete_shared(driver, second, "A done" if second == "A" else '{"project":"B"}')
        result_a, result_b = await asyncio.wait_for(asyncio.gather(a, b), 5)
        assert result_a["state"] == result_b["state"] == "completed"
        assert result_a["text"] == "A done" and json.loads(result_b["text"]) == {"project": "B"}
        assert result_a["cleanupVerified"] and result_b["cleanupVerified"]
        assert result_a["witness"]["serverPid"] == result_b["witness"]["serverPid"] == pid
        assert not result_a["witness"]["sharedProcessDead"] and driver.pipe.process.poll() is None
        assert driver.test_owner_events == [True] and not driver.protocol.slots
    finally:
        release.set()
        await driver.close()
        await asyncio.gather(a, b, return_exceptions=True)
    assert driver.test_owner_events == [True, False]
    assert driver.shutdowns[-1]["ownedGroupCleanupVerified"] and driver.shutdowns[-1]["operationRemoved"]


@pytest.mark.asyncio
async def test_owned_shared_pipe_interrupt_ack_never_releases_target_or_stops_neighbor(tmp_path):
    driver = shared_peer(tmp_path, interrupt_completes=False)
    ready_a, ready_b = asyncio.Event(), asyncio.Event()
    value_a = shared_input("A", started=ready_a.set)
    a = asyncio.create_task(driver.run(value_a))
    b = asyncio.create_task(driver.run(shared_input("B", started=ready_b.set)))
    try:
        await asyncio.wait_for(asyncio.gather(ready_a.wait(), ready_b.wait()), 5)
        pid = driver.pipe.process.pid
        value_a.cancelled.set()
        complete_shared(driver, "B", "Neighbor completed")
        result_b = await asyncio.wait_for(b, 5)
        assert result_b["state"] == "completed" and not a.done()
        assert driver.live["A"].slot.interrupt_requested and not driver.live["A"].slot.released
        assert driver.pipe.process.pid == pid and driver.pipe.process.poll() is None
        slot = driver.live["A"].slot
        emit_shared(driver, {"method": "turn/completed", "params": {"threadId": slot.thread,
            "turn": {"id": slot.turn, "status": "interrupted"}}})
        result_a = await asyncio.wait_for(a, 5)
        assert result_a["state"] == "cancelled" and result_a["error"] == "CANCELLED" and result_a["cleanupVerified"]
        assert not driver.fenced and driver.pipe.process.poll() is None
    finally:
        await driver.close()
        await asyncio.gather(a, b, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["none", "missing", "negative", "string", "bool", "not-object"])
async def test_native_usage_projects_supported_counters_without_crossing_turns(tmp_path, fault):
    driver = shared_peer(tmp_path)
    ready_a, ready_b = asyncio.Event(), asyncio.Event()
    tasks = [asyncio.create_task(driver.run(shared_input(job, started=ready.set)))
        for job, ready in (("A", ready_a), ("B", ready_b))]
    try:
        await asyncio.wait_for(asyncio.gather(ready_a.wait(), ready_b.wait()), 5)
        expected = dict(inputTokens=6, cachedInputTokens=2, outputTokens=4, totalTokens=10)
        counters = {**expected, "cacheWriteInputTokens": 0, "reasoningOutputTokens": 3}
        if fault == "missing": del counters["totalTokens"]
        elif fault == "negative": counters["inputTokens"] = -1
        elif fault == "string": counters["inputTokens"] = "6"
        elif fault == "bool": counters["inputTokens"] = True
        elif fault == "not-object": counters = []
        slot = driver.live["A"].slot
        emit_shared(driver, {"method": "thread/tokenUsage/updated", "params": {
            "threadId": slot.thread, "turnId": slot.turn, "tokenUsage": {"total": counters}}})
        if fault == "none":
            for _ in range(100):
                if driver.live["A"].usage == expected: break
                await asyncio.sleep(.01)
            assert driver.live["A"].usage == expected and driver.live["B"].usage["totalTokens"] == 1
            assert not driver.fenced
            complete_shared(driver, "A", "A result")
            complete_shared(driver, "B", "B result")
        results = await asyncio.wait_for(asyncio.gather(*tasks), 5)
        assert all(result["cleanupVerified"] for result in results)
        if fault == "none":
            assert results[0]["usage"] == expected and all(result["state"] == "completed" for result in results)
        else:
            assert driver.fenced and all(result["state"] == "failed" for result in results)
    finally:
        await driver.close()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_owned_shared_pipe_crash_fences_every_turn_and_verifies_real_process_death(tmp_path):
    driver = shared_peer(tmp_path)
    ready_a, ready_b = asyncio.Event(), asyncio.Event()
    tasks = [asyncio.create_task(driver.run(shared_input(job, started=event.set)))
        for job, event in (("A", ready_a), ("B", ready_b))]
    try:
        await asyncio.wait_for(asyncio.gather(ready_a.wait(), ready_b.wait()), 5)
        pipe = driver.pipe
        pipe.send({"method": "fixture/exit", "params": {"code": 9}})
        results = await asyncio.wait_for(asyncio.gather(*tasks), 5)
        assert driver.fenced and pipe.process.poll() == 9
        assert all(result["state"] == "failed" and result["cleanupVerified"] for result in results)
        assert all(result["witness"]["sharedProcessDead"] for result in results)
        with pytest.raises(TransportFailure, match="ACCOUNT_FENCED"):
            await driver.run(shared_input("C"))
    finally:
        await driver.close()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_owned_shared_pipe_rotates_only_when_idle_and_retains_profile_owner(tmp_path):
    driver = shared_peer(tmp_path, limits=ProtocolLimits(threads_per_server=2))
    try:
        previous_pid = None
        for index in range(3):
            ready = asyncio.Event()
            name = "job_" + str(index)
            task = asyncio.create_task(driver.run(shared_input(name, started=ready.set)))
            await asyncio.wait_for(ready.wait(), 5)
            if index == 1:
                with pytest.raises(TransportFailure, match="SERVER_ROTATION_REQUIRED"):
                    await driver.prepare()
                previous_pid = driver.pipe.process.pid
            complete_shared(driver, name, name)
            result = await asyncio.wait_for(task, 5)
            assert result["cleanupVerified"]
        assert driver.generation == 2 and driver.pipe.process.pid != previous_pid
        assert driver.shutdowns[0]["ownedGroupCleanupVerified"] and driver.test_owner_events == [True]
    finally:
        await driver.close()


async def shared_job_environment(root, server):
    import httpx
    from tests.recovery.test_background_agent import environment
    from resume_api.agent.service import AgentConnection
    from resume_api.jobs.runtime import JobRuntime
    from resume_api.jobs.fixed_runtime import FixedRuntime
    from resume_api.jobs.appserver import SharedAgentRuntime, CapabilityClient
    from packages.resume_core.models.agent import AgentSettingsRequest
    service, factory, workspace, payload, connection, old = await environment(root)
    current = service.projects.workspaces[workspace.project_id]
    next(block for block in current.project.document.blocks() if block.id == "narrative").content[0].text = root.name + " private evidence"
    assert service.projects.persist(workspace.project_id) == "durable"
    workspace = service.projects.storage.read_committed(workspace.project_id)[0]
    connection["value"] = AgentConnection(True, ("gpt-6-luna",), "account_1")
    service.settings.save(AgentSettingsRequest(expectedRevision=2, enabled=True,
        selectedAgentModel="gpt-6-luna"), connection["value"].models)
    payload.request.settings_revision = 3
    def client(value):
        session = service.supervisor.active.owned.session
        assert value.token == session.token and value.url == session.url
        return CapabilityClient(value, transport=httpx.ASGITransport(app=session))
    service.runtime = SharedAgentRuntime(server, native=False, client_factory=client)
    service.supervisor.factory = lambda job, model: (JobRuntime(service, job, model)
        if job.submission.kind == "agent" else FixedRuntime(service, job, model))
    ready = asyncio.Queue()
    async def observe(name, identifier):
        if name in {"scripted_model_ready", "scripted_fixed_model_ready"}:
            await ready.put(identifier)
    service.supervisor.observer = observe
    return service, factory, workspace, payload, ready


async def shared_tool(driver, job, name, arguments, number):
    live = driver.live[job]
    identifier = "call_" + str(number)
    emit_shared(driver, tool_frame(live.slot, identifier=number, call=identifier, tool=name, arguments=arguments))
    async def response():
        while True:
            live.changed.clear()
            call = live.slot.calls.get(identifier)
            if call is not None and call.response is not None:
                value = call.response
                assert "result" in value, value
                return json.loads(value["result"]["contentItems"][0]["text"])
            if live.error:
                raise AssertionError(live.error)
            await live.changed.wait()
    return await asyncio.wait_for(response(), 5)


async def prepare_shared_proposal(driver, job, *, first_call=100):
    from packages.resume_core.models.agent import AgentReadSnapshot
    from tests.recovery.test_agent_edits import command, replace
    read = await shared_tool(driver, job, "get_resume_context", {"query": {"kind": "document", "ids": ["narrative"]}}, first_call)
    snapshot = AgentReadSnapshot.model_validate(read["snapshot"])
    prepared = await shared_tool(driver, job, "prepare_edit_batch",
        {"request": command(replace(snapshot, "narrative", 0, 6, "Clear")).model_dump(by_alias=True)}, first_call + 1)
    assert prepared["disposition"] == "prepared", prepared
    applied = await shared_tool(driver, job, "apply_edit_batch", {"request": {"batchId": prepared["batchId"]}}, first_call + 2)
    assert applied.get("proposalStored"), applied
    return applied


async def job_ready(service, job, queue):
    task = asyncio.create_task(queue.get())
    control = service.supervisor.controls.get(job.id)
    try:
        if control is None:
            return await asyncio.wait_for(task, 5)
        done, _ = await asyncio.wait((task, control.task), timeout=5, return_when=asyncio.FIRST_COMPLETED)
        assert task in done, (service.store.read(control.project_id, job.id),
            getattr(control.owned, "result", None), control.run_task.result() if control.run_task and control.run_task.done() else None)
        return await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def shared_publication_flow(tmp_path, *, cleanup_failure=False, monkeypatch=None):
    from tests.recovery.test_background_agent import hold_writer
    from packages.resume_core.agent_store import digest
    from packages.resume_core.background_store import JobStore
    server = shared_peer(tmp_path / "transport")
    profile = None
    failed_pipe = None
    if cleanup_failure:
        import threading
        import time
        from resume_api.profile_ownership import native_profile
        class EmptyProfile:
            root = tmp_path / "empty-profile"
            def prepare(self):
                self.root.mkdir(mode=0o700, exist_ok=True)
        profile = EmptyProfile()
        server.owner = lambda: native_profile(profile, threading.Event(), deadline=time.monotonic() + 1,
            blocking=False, operations_root=server.root)
    service_a, factory_a, workspace_a, payload_a, ready_a = await shared_job_environment(tmp_path / "A", server)
    service_b, factory_b, workspace_b, payload_b, ready_b = await shared_job_environment(tmp_path / "B", server)
    proof = hold_writer(service_a, workspace_a)
    before = digest(service_a.projects.storage.read_committed(workspace_a.project_id)[0])
    try:
        job_a, _ = await service_a.submit(workspace_a.project_id, payload_a)
        job_b, _ = await service_b.submit(workspace_b.project_id, payload_b)
        assert await job_ready(service_a, job_a, ready_a) == job_a.id
        assert await job_ready(service_b, job_b, ready_b) == job_b.id
        a, b = server.live[job_a.id], server.live[job_b.id]
        assert a.server_pid == b.server_pid and a.slot.thread != b.slot.thread
        denied = await shared_tool(server, job_a.id, "get_resume_context", {"query": {"kind": "document", "ids": ["foreign-block"]}}, 100)
        assert denied.get("error") or not json.loads(denied["content"])["blocks"]
        pending = await prepare_shared_proposal(server, job_a.id, first_call=200)
        saved = await prepare_shared_proposal(server, job_b.id, first_call=300)
        assert pending["disposition"] == "waiting_for_sync" and not pending["durable"]
        assert saved["disposition"] == "saved" and saved["durable"]
        complete_shared(server, job_a.id, "Правка ожидает безопасного сохранения.")
        complete_shared(server, job_b.id, "Правка сохранена.")
        await asyncio.wait_for(asyncio.gather(service_a.supervisor.controls[job_a.id].task,
            service_b.supervisor.controls[job_b.id].task), 5)
        result_a = service_a.store.read(workspace_a.project_id, job_a.id)
        result_b = service_b.store.read(workspace_b.project_id, job_b.id)
        assert result_a.execution == result_b.execution == "completed"
        assert result_a.publication == "waiting_for_sync" and result_a.receipt is None
        assert result_b.publication == "saved" and result_b.receipt.durable
        assert result_a.attempts[-1].cleanup_verified and result_b.attempts[-1].cleanup_verified
        assert not result_a.attempts[-1].native_started and not result_b.attempts[-1].native_started
        assert not service_a.admission.locked() and not service_b.admission.locked() and server.pipe.process.poll() is None
        assert digest(service_a.projects.storage.read_committed(workspace_a.project_id)[0]) == before
        if cleanup_failure:
            from packages.resume_core.models.background import WriterCheckpointV1
            from tests.recovery.test_background_inverse import mutation, put
            baseline, checksum = service_a.projects.storage.read_committed(workspace_a.project_id)
            document = baseline.project.document.model_copy(deep=True)
            next(block for block in document.blocks() if block.id == "quote").content[0].text = "Retained local draft"
            change = mutation(baseline, [put(baseline, "quote", text="Retained local draft")], "retained-draft")
            change.capture.session_id = proof.session_id
            service_a.writers.checkpoint(workspace_a.project_id, WriterCheckpointV1(schemaVersion=1, proof=proof,
                id="transport-rollback-draft", sequence=1, actionCursor=1, baseRevision=baseline.project_revision,
                baseSha256=checksum, payload=dict(schemaVersion=1, document=document.model_dump(by_alias=True),
                    facts=baseline.project.facts.model_dump(by_alias=True),
                    touches=[dict(cursor=1, mutation=change.model_dump(by_alias=True))], outbox=[], assetPins=[])))
        state = service_a.store.load(workspace_a.project_id)
        await service_a.disable()
        await service_b.disable()
        if cleanup_failure:
            from resume_api.lifecycle import SpikeError, has_blocked_owned
            from resume_api.profile_ownership import recover_profile
            failed_pipe = server.pipe
            def fail():
                raise SpikeError("PROCESS_CLEANUP_FAILED")
            monkeypatch.setattr(failed_pipe.files, "stop_worker", fail)
            with pytest.raises(SpikeError, match="PROCESS_CLEANUP_FAILED"):
                await server.close()
            assert failed_pipe.process.poll() is None and not failed_pipe.cleanup_verified
            assert has_blocked_owned(server.root) and recover_profile(profile, server.root)
            assert (profile.root / ".foldcv-inference-blocked").exists()
        else:
            await server.close()
        restored = JobStore(service_a.store.root).load(workspace_a.project_id)
        assert restored.proposals == state.proposals and restored.jobs[0].receipt is None
        assert restored.drafts == state.drafts and (not cleanup_failure or len(restored.drafts) == 1)
        assert restored.jobs[0].publication == "waiting_for_sync" and restored.proposals[0].authority == "active"
        assert digest(service_a.projects.storage.read_committed(workspace_a.project_id)[0]) == before
        assert JobStore(service_b.store.root).read(workspace_b.project_id, job_b.id).receipt == result_b.receipt
        assert not service_a.accepting and not service_b.accepting
    finally:
        await service_a.shutdown()
        await service_b.shutdown()
        if failed_pipe is not None:
            from spikes.cli.runner import stop_group
            await asyncio.to_thread(stop_group, failed_pipe.process)
            for stream in (failed_pipe.process.stdin, failed_pipe.process.stdout, failed_pipe.process.stderr):
                stream.close()
            assert failed_pipe.process.poll() is not None
        else:
            await server.close()
        factory_a.verify(); factory_b.verify()
        service_a.supervisor.clock.verify(); service_b.supervisor.clock.verify()


@pytest.mark.asyncio
async def test_shared_agent_capabilities_use_real_compiler_and_keep_deferred_save_after_transport_exit(tmp_path):
    await shared_publication_flow(tmp_path)


@pytest.mark.asyncio
async def test_cleanup_failure_and_flag_rollback_preserve_durable_state(tmp_path, monkeypatch):
    await shared_publication_flow(tmp_path, cleanup_failure=True, monkeypatch=monkeypatch)


@pytest.mark.asyncio
async def test_shared_fixed_rewrite_publishes_captured_output_while_agent_turn_stays_live(tmp_path):
    import threading
    from packages.resume_core.text_rewrite import PlainTextReply
    from resume_api.jobs.appserver import SharedContentProvider
    from resume_api.providers.content import ContentInput, GenerationPolicy
    from tests.recovery.generation_fixtures import CreationProvider
    from tests.recovery.test_background_fixed_jobs import fixed_request, rewrite_command, settled
    server = shared_peer(tmp_path / "transport")
    a, fa, wa, pa, ra = await shared_job_environment(tmp_path / "A", server)
    b, fb, wb, _pb, rb = await shared_job_environment(tmp_path / "B", server)
    provider = SharedContentProvider(server, native=False)
    b.projects.provider_factory = lambda: (provider, "gpt-6-luna")
    try:
        job_a, _ = await a.submit(wa.project_id, pa)
        reply, _ = await b.fixed.submit(wb.project_id, fixed_request(b, wb.project_id,
            "shared-rewrite", rewrite_command(wb)))
        assert await job_ready(a, job_a, ra) == job_a.id
        assert await job_ready(b, reply.job, rb) == reply.job.id
        live = server.live[reply.job.id]
        assert live.value.output_schema is None and live.value.plain_text and not live.value.tools
        fixture_request = ContentInput(live.value.prompt, PlainTextReply,
            GenerationPolicy(model="gpt-6-luna", allow_repair=False))
        output = CreationProvider().generate(fixture_request, None, threading.Event()).value
        complete_shared(server, live.slot.job, output.text)
        result_b = await settled(b, wb.project_id, reply.job.id, publication="saved")
        assert result_b.execution == "completed" and len(result_b.attempts) == 1
        assert result_b.attempts[-1].cleanup_verified and not result_b.attempts[-1].native_started
        assert job_a.id in server.live and server.pipe.process.poll() is None
        saved = b.projects.storage.read_committed(wb.project_id)[0]
        assert "Clearer:" in next(block for block in saved.project.document.blocks() if block.id == "narrative").content[0].text
        complete_shared(server, job_a.id, "Проверка завершена.")
        await asyncio.wait_for(a.supervisor.controls[job_a.id].task, 5)
        assert a.store.read(wa.project_id, job_a.id).execution == "completed"
    finally:
        await a.shutdown(); await b.shutdown(); await server.close()
        fa.verify(); fb.verify()
        a.supervisor.clock.verify(); b.supervisor.clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["deadline", "text", "normalized"])
async def test_shared_turn_limits_stop_only_the_target_and_preserve_neighbor(tmp_path, fault):
    from packages.resume_core.background_clock import ControlledDeadlines
    clock = ControlledDeadlines()
    server = shared_peer(tmp_path, clock=clock)
    ra, rb = asyncio.Event(), asyncio.Event()
    fault_active = False
    def emit(_kind, _value):
        if fault == "normalized" and fault_active:
            raise TransportFailure("NORMALIZED_OUTPUT_LIMIT")
    a = asyncio.create_task(server.run(shared_input("A", started=ra.set, text_limit=8, emit=emit)))
    b = None
    try:
        await asyncio.wait_for(ra.wait(), 5)
        clock.advance(50)
        b = asyncio.create_task(server.run(shared_input("B", started=rb.set)))
        await asyncio.wait_for(rb.wait(), 5)
        # Inject the failure after both turns start, not during startup events.
        fault_active = True
        if fault == "deadline":
            clock.advance(130)
        else:
            slot = server.live["A"].slot
            emit_shared(server, {"method": "item/agentMessage/delta", "params": {"threadId": slot.thread,
                "turnId": slot.turn, "delta": "too many bytes" if fault == "text" else "short"}})
        result_a = await asyncio.wait_for(a, 5)
        assert result_a["state"] == "failed" and result_a["cleanupVerified"]
        assert result_a["error"] == {"deadline": "DEADLINE", "text": "TEXT_LIMIT", "normalized": "NORMALIZED_OUTPUT_LIMIT"}[fault]
        assert not server.fenced and "B" in server.live and server.pipe.process.poll() is None
        complete_shared(server, "B", "Neighbor succeeds")
        result_b = await asyncio.wait_for(b, 5)
        assert result_b["state"] == "completed" and result_b["cleanupVerified"]
    finally:
        await server.close()
        await asyncio.gather(*(task for task in (a, b) if task is not None), return_exceptions=True)
        clock.verify()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["none", "wrong-project", "trailing-data", "invalid-field", "tool-activity"])
async def test_shared_structured_turn_keeps_existing_strict_validator_without_repair(tmp_path, fault):
    import threading
    from typing import Literal
    from pydantic import BaseModel, ConfigDict
    from resume_api.jobs.appserver import SharedContentProvider
    from resume_api.providers.content import ContentInput, GenerationPolicy, ContentFailure
    class Output(BaseModel):
        model_config = ConfigDict(extra="forbid")
        project: Literal["B"]
        text: str
    server = shared_peer(tmp_path)
    wire_frames = []
    server.wire_audit = wire_frames.append
    ready = asyncio.Event()
    audits = []
    provider = SharedContentProvider(server, native=False, audit=audits.append)
    provider.loop, provider.job_id, provider.cancelled = asyncio.get_running_loop(), "fixed_B", asyncio.Event()
    provider.model_started = ready.set
    value = {"project": "A" if fault == "wrong-project" else "B", "text": "B private result"}
    if fault == "invalid-field": value["unknown"] = "not accepted"
    task = asyncio.create_task(provider.execute(ContentInput("B captured context", Output,
        GenerationPolicy(model="gpt-6-luna", allow_repair=False)), threading.Event()))
    try:
        await asyncio.wait_for(ready.wait(), 5)
        from spikes.cli.profile import DISABLED_FEATURES
        request = next(row["frame"] for row in wire_frames if row["direction"] == "client" and row["frame"].get("method") == "thread/start")
        features = request["params"]["config"]["features"]
        assert all(features[name] is False for name in DISABLED_FEATURES)
        assert features["skip_host_skill_discovery"] is True and features["guardian_approval"] is False
        if fault == "tool-activity":
            live = server.live["fixed_B"]
            emit_shared(server, {"method": "item/started", "params": {"threadId": live.slot.thread,
                "turnId": live.slot.turn, "item": {"id": "bad", "type": "commandExecution"}}})
        else:
            complete_shared(server, "fixed_B", json.dumps(value) + (" trailing" if fault == "trailing-data" else ""))
        if fault == "none":
            result = await asyncio.wait_for(task, 5)
            assert result.value.project == "B" and result.logical_attempts == 1
            assert audits[-1]["schemaValidated"] is True
        else:
            with pytest.raises(ContentFailure):
                await asyncio.wait_for(task, 5)
            assert not any(record.get("schemaValidated") for record in audits)
        assert server.protocol.thread_starts == 1 and provider.sequence == 1 and not server.live
    finally:
        await server.close()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_owned_pipe_close_wakes_a_pending_reader_without_leaking_a_waiter(tmp_path):
    peer = await pipe_peer(tmp_path).start()
    pending = asyncio.create_task(peer.receive())
    await peer.close()
    with pytest.raises(TransportFailure, match="SERVER_CLOSED"):
        await asyncio.wait_for(pending, 3)


@pytest.mark.asyncio
async def test_pipe_cleanup_inventory_exception_never_allows_runtime_or_command_discovery(tmp_path):
    import os
    import subprocess
    from resume_api.cli.experimental_profile import BINARY
    from resume_api.agent.runtime import CodexAgentRuntime
    peer = await pipe_peer(tmp_path).start()
    try:
        result = subprocess.run(["/bin/ps", "-axo", "pid=,pgid=,stat="], capture_output=True,
            env={"PATH": os.defpath, "LC_ALL": "C"}, timeout=1)
        assert result.returncode == 0
        for command in ([str(BINARY), "app-server"], ["/bin/ps", "-axo", "pid=,command="], ["/bin/sh", "-c", "true"]):
            with pytest.raises(AssertionError, match="unregistered child spawn"):
                subprocess.Popen(command)
        with pytest.raises(AssertionError, match="production runtime/connection factory"):
            CodexAgentRuntime(None, tmp_path)
    finally:
        await peer.close()


@pytest.mark.asyncio
async def test_shared_plain_rewrite_has_no_schema_tools_or_agent_instructions_and_uses_low(tmp_path):
    import threading
    from packages.resume_core.text_rewrite import PlainTextReply, plain_prompt
    from resume_api.jobs.appserver import SharedContentProvider
    from resume_api.providers.content import ContentInput, GenerationPolicy
    server = shared_peer(tmp_path)
    frames, audits, ready = [], [], asyncio.Event()
    server.wire_audit = frames.append
    provider = SharedContentProvider(server, native=False, audit=audits.append)
    provider.loop, provider.job_id, provider.cancelled = asyncio.get_running_loop(), "plain-edit", asyncio.Event()
    provider.model_started = ready.set
    task = asyncio.create_task(provider.execute(ContentInput(plain_prompt("Clarify", "Selected text"), PlainTextReply,
        GenerationPolicy(model="gpt-6-luna", reasoning_effort="low", allow_repair=False)), threading.Event()))
    try:
        await asyncio.wait_for(ready.wait(), 5)
        requests = [row["frame"] for row in frames if row["direction"] == "client"]
        thread = next(row["params"] for row in requests if row.get("method") == "thread/start")
        turn = next(row["params"] for row in requests if row.get("method") == "turn/start")
        assert thread["dynamicTools"] == [] and thread["config"]["web_search"] == "disabled"
        assert thread["config"]["features"]["code_mode"] is False
        assert "resume assistant" not in thread["baseInstructions"]
        assert thread["config"]["model_reasoning_effort"] == turn["effort"] == "low"
        assert "outputSchema" not in turn
        complete_shared(server, "plain-edit", "Clear plain text.")
        result = await asyncio.wait_for(task, 5)
        assert result.value.text == "Clear plain text." and result.logical_attempts == 1
        assert audits[-1]["textValidated"] and not audits[-1]["schemaValidated"]
    finally:
        await server.close()
        await asyncio.gather(task, return_exceptions=True)
