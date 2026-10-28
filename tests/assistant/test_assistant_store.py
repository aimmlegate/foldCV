"""Assistant files (assistant_store): failed writes change nothing, damaged or linked files are refused, lists stay bounded."""

import pytest

from packages.resume_core import agent_limits as limits
from packages.resume_core.assistant_store import FILE_BYTES, AgentFailure, AssistantStore
from packages.resume_core.models.agent import AgentMessage, AgentWebSource

PROJECT = "template-project"


def message(index, role="user", text=None, run="run_1"):
    return AgentMessage(id="message_" + str(index), role=role, text=text or "Synthetic question " + str(index),
        runId=run, timestamp="2026-10-15T12:00:00+00:00", sources=[], findings=[], truncated=False, error=None)


def source(index, run):
    url = "https://public.example/" + str(index)
    return AgentWebSource(id="source_" + str(index), runId=run, requestedUrl=url, finalUrl=url, title="Synthetic page",
        retrievedAt="2026-10-15T12:00:00+00:00", contentSha256="a" * 64, text="я" * 30000, truncated=False,
        originalBytes=60000)


def test_a_failed_atomic_write_keeps_the_previous_file_and_reports_the_failure(tmp_path, monkeypatch):
    store = AssistantStore(tmp_path)
    conversation = store.create_conversation(PROJECT, "Synthetic")
    path = store.directory(PROJECT, "conversations", conversation.id + ".json")
    original = path.read_bytes()

    def denied(*_):
        raise OSError("synthetic write failure")
    monkeypatch.setattr("packages.resume_core.assistant_store.atomic_write", denied)
    with pytest.raises(AgentFailure, match="AGENT_SAVE_FAILED"):
        store.update_conversation(PROJECT, conversation.id, lambda value: value.messages.append(message(0)))
    assert path.read_bytes() == original and store.conversation(PROJECT, conversation.id).messages == []


def test_damaged_linked_foreign_and_unsafe_files_are_refused_and_left_unchanged(tmp_path):
    store = AssistantStore(tmp_path)
    conversation = store.create_conversation(PROJECT)
    path = store.directory(PROJECT, "conversations", conversation.id + ".json")
    damaged = b'{"schemaVersion":1,"schemaVersion":2}'
    path.write_bytes(damaged)
    with pytest.raises(AgentFailure, match="AGENT_STORE_UNAVAILABLE"):
        store.conversation(PROJECT, conversation.id)
    assert path.read_bytes() == damaged
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_text("synthetic private bytes")
    path.symlink_to(outside)
    with pytest.raises(AgentFailure, match="AGENT_STORE_UNAVAILABLE"):
        store.conversations(PROJECT)
    assert outside.read_text() == "synthetic private bytes"
    other = store.create_conversation("other-project")
    with pytest.raises(AgentFailure, match="AGENT_NOT_FOUND"):
        store.conversation(PROJECT, other.id)
    for unsafe in ("../other-project", "/etc/passwd"):
        with pytest.raises(AgentFailure, match="AGENT_NOT_FOUND"):
            store.conversation(PROJECT, unsafe)


def test_a_conversation_keeps_only_the_last_messages(tmp_path):
    store = AssistantStore(tmp_path)
    conversation = store.create_conversation(PROJECT)
    store.update_conversation(PROJECT, conversation.id,
        lambda value: value.messages.extend(message(index) for index in range(limits.CONVERSATION_MESSAGES + 5)))
    kept = store.conversation(PROJECT, conversation.id).messages
    assert len(kept) == limits.CONVERSATION_MESSAGES and kept[0].id == "message_5"
    assert kept[-1].id == "message_" + str(limits.CONVERSATION_MESSAGES + 4)


def test_a_conversation_over_the_file_limit_drops_its_oldest_turns_and_stays_writable(tmp_path):
    # Twenty turns of three full page reads and a long answer are far below the count bounds and above 4 MiB.
    store = AssistantStore(tmp_path)
    conversation = store.create_conversation(PROJECT)
    path = store.directory(PROJECT, "conversations", conversation.id + ".json")
    for turn in range(20):
        run = "run_" + str(turn)

        def change(value, turn=turn, run=run):
            value.messages.append(message(turn * 2, run=run))
            value.sources.extend(source(turn * 3 + index, run) for index in range(3))
            value.messages.append(message(turn * 2 + 1, "assistant", "я" * 30000, run))
        store.update_conversation(PROJECT, conversation.id, change)
        assert path.stat().st_size <= FILE_BYTES
    kept = store.conversation(PROJECT, conversation.id)
    assert [item.id for item in kept.sources if item.run_id == "run_19"] == ["source_57", "source_58", "source_59"]
    assert [item.id for item in kept.messages[-2:]] == ["message_38", "message_39"]
    assert kept.messages[0].run_id != "run_0" and kept.sources[0].run_id != "run_0"
