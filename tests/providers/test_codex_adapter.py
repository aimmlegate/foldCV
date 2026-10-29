"""CodexCliProvider over a fake CLI process: protocol, budgets, deadlines, cancellation, cleanup. No live provider."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import threading
import time
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field
import pytest

from resume_api.lifecycle import OperationFiles, SpikeError, has_blocked_owned
from resume_api.providers.codex_cli import CodexCliProvider, FixtureTransport, strict_json
from resume_api.providers.content import ContentFailure, ContentInput, GenerationPolicy
from tests.providers.fixtures import PROMPT, Summary, fake, request


class Heading(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    heading: str = Field(min_length=1, max_length=80)


def test_encoded_transport_size_is_bounded_before_cli_dispatch(fake):
    from dataclasses import replace

    class Oversized:
        def encode(self, _text):
            return "x" * (256 * 1024 + 1)

        def restore(self, value):
            return value

    cli, root, keep, _configure, starts = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files, pytest.raises(ContentFailure) as error:
        provider.generate(replace(request(), transport=Oversized()), files, threading.Event())
    assert error.value.code == "INPUT_TOO_LARGE" and starts() == 0
    assert list(root.iterdir()) == [keep]


def generate(fake, *, case: str = "valid", fixture: bool = True, **config: object):
    cli, root, keep, configure, starts = fake
    configure(case, **config)
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli) if fixture else None)
    with OperationFiles(root).open() as files:
        value = provider.generate(request(), files, threading.Event())
    assert list(root.iterdir()) == [keep]
    return value, starts()


def failure(fake, case: str, code: str, expected_starts: int, **config: object) -> ContentFailure:
    cli, root, keep, configure, starts = fake
    configure(case, **config)
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with pytest.raises(ContentFailure) as raised:
        with OperationFiles(root).open() as files:
            provider.generate(request(), files, threading.Event())
    assert raised.value.code == code
    assert PROMPT not in str(raised.value) and "synthetic-secret" not in str(raised.value)
    assert starts() == expected_starts
    assert list(root.iterdir()) == [keep]
    return raised.value


def test_success_reports_usage_and_native_metadata_without_idle_generation(fake) -> None:
    cli, root, keep, _, starts = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        assert provider.probe(files, threading.Event()).generation_ready
        assert provider.list_models(files, threading.Event()) == ("gpt-6-luna",)
    assert starts() == 0
    assert list(root.iterdir()) == [keep]
    result, count = generate(fake)
    assert result.value.summary == "Fictional engineer builds small services."
    assert result.usage.input_tokens == 100 and result.usage.output_tokens == 12
    assert result.usage.complete and result.internal_inference_count is None
    assert result.logical_attempts == count == 1


def test_rewrite_diagnostics_separate_cli_preflight_startup_and_model_turn(fake, tmp_path):
    from resume_api.rewrite_timing import rewrite_timing
    with rewrite_timing(tmp_path / "diagnostics-root", 1):
        result, count = generate(fake)
    row, = json.loads((tmp_path / "diagnostics-root/diagnostics/rewrite-timings.json").read_text())
    phases = row["milliseconds"]
    assert {"preflight", "cli_startup", "model_turn", "cli_process", "decode", "total"} <= phases.keys()
    assert phases["cli_process"] >= phases["model_turn"]
    assert PROMPT not in json.dumps(row) and count == result.logical_attempts == 1


@pytest.mark.parametrize("case,code", [
    ("malformed_event", "INVALID_RESULT"), ("invalid_utf8", "INVALID_RESULT"),
    ("utf16", "INVALID_RESULT"), ("utf32", "INVALID_RESULT"),
    ("bad_usage", "INVALID_RESULT"), ("incomplete", "INCOMPLETE_STREAM"),
    ("unterminated", "INCOMPLETE_STREAM"), ("duplicate_completion", "INVALID_RESULT"),
    ("duplicate_message", "INVALID_RESULT"), ("out_of_order", "INVALID_RESULT"),
    ("unknown_event", "INVALID_RESULT"), ("tool", "UNEXPECTED_TOOL_ACTIVITY"),
    ("nonzero_after_complete", "CLI_FAILED"), ("nonzero", "CLI_FAILED"),
    ("quota", "RATE_LIMITED"), ("expired", "AUTH_REQUIRED"),
    ("bad_error_code", "CLI_FAILED"),
    ("usage_limit", "QUOTA_EXHAUSTED"), ("usage_limit_turn", "QUOTA_EXHAUSTED"), ("plain_error", "CLI_FAILED"),
    ("invalid_startup_warning", "INVALID_RESULT"),
    ("model_denied", "MODEL_DENIED"), ("excessive", "OUTPUT_TOO_LARGE"),
    ("excessive_stderr", "OUTPUT_TOO_LARGE"),
])
def test_protocol_failures_are_terminal(fake, case: str, code: str) -> None:
    failure(fake, case, code, 1)


def test_fragmented_utf8_unknown_optional_and_unknown_usage(fake) -> None:
    result, count = generate(fake, case="fragmented")
    assert result.value.summary == "Вымышленный инженер ☃"
    assert count == 1
    result, count = generate(fake, case="missing_usage")
    assert result.usage.input_tokens is None and result.usage.output_tokens is None
    assert not result.usage.complete and result.internal_inference_count is None
    assert count == 2


def test_intermediate_agent_message_does_not_replace_structured_final_or_start_repair(fake) -> None:
    result, count = generate(fake, case="intermediate_message")
    assert result.value.summary == "Fictional engineer builds small services."
    assert result.usage.input_tokens == 100 and result.usage.output_tokens == 12
    assert result.logical_attempts == count == 1


def test_nonfatal_startup_error_item_preserves_final_result_and_usage(fake) -> None:
    result, count = generate(fake, case="startup_warning")
    assert result.value.summary == "Fictional engineer builds small services."
    assert result.usage.input_tokens == 100 and result.usage.complete
    assert result.logical_attempts == count == 1


def test_valid_intermediate_message_cannot_hide_invalid_final_response(fake) -> None:
    error = failure(fake, "intermediate_invalid_final", "INVALID_RESULT", 2)
    assert error.logical_attempts == 2 and error.usage.input_tokens == 200


@pytest.mark.parametrize("elapsed", [31, 61, 179, 181])
def test_long_policy_waits_past_thirty_seconds_but_keeps_its_bounded_deadline(fake, monkeypatch, elapsed) -> None:
    cli, root, keep, configure, starts = fake
    now = [0.0]
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli), clock=lambda: now[0])
    run_process = provider.process.run

    def delayed_run(files, args, **kwargs):
        accept = kwargs.get("on_line")
        if args[0] == "exec" and accept is not None:
            def delayed_line(raw):
                if json.loads(raw)["type"] == "turn.completed":
                    now[0] = elapsed
                return accept(raw)
            kwargs["on_line"] = delayed_line
        return run_process(files, args, **kwargs)

    monkeypatch.setattr(provider.process, "run", delayed_run)
    policy = GenerationPolicy("gpt-6-luna", timeout_seconds=180)
    with OperationFiles(root).open() as files:
        if elapsed < 180:
            result = provider.generate(ContentInput(PROMPT, Summary, policy), files, threading.Event())
            assert result.value.summary == "Fictional engineer builds small services."
            assert result.logical_attempts == 1 and result.usage.input_tokens == 100
        else:
            with pytest.raises(ContentFailure) as raised:
                provider.generate(ContentInput(PROMPT, Summary, policy), files, threading.Event())
            assert raised.value.code == "DEADLINE_EXCEEDED"
            assert raised.value.logical_attempts == 1
    assert starts() == 1 and list(root.iterdir()) == [keep]


def test_output_contract_is_code_owned_and_generic(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("valid", schema_required=["heading"], result_text='{"heading":"Synthetic heading"}')
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        result = provider.generate(ContentInput(PROMPT, Heading, GenerationPolicy("gpt-6-luna", timeout_seconds=60)),
                                   files, threading.Event())
    assert result.value.heading == "Synthetic heading"
    assert starts() == 1 and list(root.iterdir()) == [keep]


def test_completed_invalid_output_repairs_once_with_reported_consumption(fake) -> None:
    result, count = generate(fake, case="repair")
    assert result.value.summary == "Fictional engineer builds small services."
    assert result.logical_attempts == count == 2
    assert result.usage.input_tokens == 200 and result.usage.output_tokens == 24
    assert result.usage.complete
    error = failure(fake, "schema", "INVALID_RESULT", 4)
    assert error.logical_attempts == 2 and error.usage.input_tokens == 200


def test_failed_final_attempts_keep_reported_usage(fake) -> None:
    error = failure(fake, "nonzero_after_complete", "CLI_FAILED", 1)
    assert error.logical_attempts == 1
    assert error.usage.input_tokens == 100 and error.usage.complete
    error = failure(fake, "repair_second_nonzero", "CLI_FAILED", 3)
    assert error.logical_attempts == 2
    assert error.usage.input_tokens == 200 and error.usage.complete
    error = failure(fake, "nonzero", "CLI_FAILED", 4)
    assert error.logical_attempts == 1
    assert error.usage.input_tokens is None and not error.usage.complete


def test_budget_disallows_repair_without_second_start(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("schema")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with pytest.raises(ContentFailure) as raised:
        with OperationFiles(root).open() as files:
            provider.generate(request(max_total_input_bytes=len(PROMPT.encode())), files, threading.Event())
    assert raised.value.code == "BUDGET_EXCEEDED" and raised.value.logical_attempts == 1
    assert starts() == 1 and list(root.iterdir()) == [keep]


def test_total_output_budget_includes_incomplete_second_attempt(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("schema")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    policy = GenerationPolicy("gpt-6-luna", timeout_seconds=60, max_total_output_bytes=500)
    with pytest.raises(ContentFailure) as raised:
        with OperationFiles(root).open() as files:
            provider.generate(ContentInput(PROMPT, Summary, policy), files, threading.Event())
    assert raised.value.code == "OUTPUT_TOO_LARGE"
    assert raised.value.logical_attempts == 2
    assert raised.value.usage.input_tokens == 100 and not raised.value.usage.complete
    assert starts() == 2 and list(root.iterdir()) == [keep]


@pytest.mark.parametrize("case,code,extra", [
    ("valid", "CLI_UNSUPPORTED", {"version": "codex-cli 0.0.1"}),
    ("valid", "CLI_PROFILE_UNSAFE", {"version": "codex-cli 0.162.0-alpha.2"}),
    ("bad_help", "CLI_PROFILE_UNSAFE", {}),
    ("unsafe_features", "CLI_PROFILE_UNSAFE", {}),
    ("api_key", "AUTH_MODE_MISMATCH", {}),
    ("missing_login", "AUTH_REQUIRED", {}),
    ("login_failure", "CLI_FAILED", {}),
    ("metadata_api_key", "AUTH_MODE_MISMATCH", {}),
    ("metadata_error", "METADATA_FAILED", {}),
])
def test_probe_and_metadata_fail_before_generation(fake, case: str, code: str, extra: dict[str, str]) -> None:
    failure(fake, case, code, 0, **extra)


def test_fixture_version_cannot_open_production_provider(fake) -> None:
    cli, root, keep, _, starts = fake
    provider = CodexCliProvider(cli)
    with OperationFiles(root).open() as files:
        assert not provider.probe(files, threading.Event()).generation_ready
        with pytest.raises(ContentFailure, match="CLI_PROFILE_UNSAFE"):
            provider.generate(request(), files, threading.Event())
    assert starts() == 0 and list(root.iterdir()) == [keep]


def test_safe_argv_environment_and_private_text_remain_in_stdin(fake) -> None:
    cli, root, _, _, _ = fake
    with patch.dict(os.environ, {name: "synthetic-secret" for name in (
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_HOME", "CODEX_MODEL", "PYTHONPATH", "HTTPS_PROXY"
    )}):
        generate(fake)
    audit = [json.loads(line) for line in (cli.parent / "audit.jsonl").read_text().splitlines()]
    assert any(entry.get("stdin_match") and entry.get("restrictions_checked") for entry in audit)
    assert PROMPT not in json.dumps(audit) and "synthetic-secret" not in json.dumps(audit)
    assert not (cli.parent.parent / "inert").exists()


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e309}',
                                        b'{"a":"\\ud800"}', b'[' * 40 + b'0' + b']' * 40])
def test_strict_json_rejects_unsafe_values(raw: bytes) -> None:
    with pytest.raises(ContentFailure, match="INVALID_RESULT"):
        strict_json(raw)


def test_pre_cancel_and_missing_executable_do_not_start(fake) -> None:
    cli, root, keep, _, starts = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ContentFailure, match="CANCELLED"):
        with OperationFiles(root).open() as files:
            provider.generate(request(), files, cancelled)
    missing = CodexCliProvider(root / "missing")
    with pytest.raises(ContentFailure, match="CLI_MISSING"):
        with OperationFiles(root).open() as files:
            missing.probe(files, threading.Event())
    assert starts() == 0 and list(root.iterdir()) == [keep]


def test_input_and_schema_fail_before_spawn(fake) -> None:
    cli, root, keep, _, starts = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))

    class Loose(BaseModel):
        summary: str

    with OperationFiles(root).open() as files:
        for candidate, code in [
            (ContentInput("☃" * 90_000, Summary, GenerationPolicy("gpt-6-luna")), "INPUT_TOO_LARGE"),
            (ContentInput(PROMPT, Summary, GenerationPolicy("--unsafe")), "MODEL_DENIED"),
            (ContentInput(PROMPT, Loose, GenerationPolicy("gpt-6-luna")), "INVALID_SCHEMA"),
        ]:
            with pytest.raises(ContentFailure, match=code):
                provider.generate(candidate, files, threading.Event())
    assert starts() == 0 and list(root.iterdir()) == [keep]


@pytest.mark.parametrize("size", [65_537, 256 * 1024])
def test_larger_complete_utf8_prompt_reaches_cli_once_without_truncation(fake, size):
    cli, root, keep, configure, starts = fake
    prompt = "Ж" * (size // 2) + (" " if size % 2 else "")
    configure(prompt=prompt)
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    policy = GenerationPolicy("gpt-6-luna", timeout_seconds=60, allow_repair=False)
    with OperationFiles(root).open() as files:
        result = provider.generate(ContentInput(prompt, Summary, policy), files, threading.Event())
    assert result.value.summary and starts() == 1
    assert len(prompt.encode()) == size and list(root.iterdir()) == [keep]


@pytest.mark.parametrize("size", [65_537, 196_608])
def test_complete_utf8_result_above_old_line_limit_uses_declared_output_budget(fake, size):
    class FullResult(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        summary: str = Field(min_length=1, max_length=256 * 1024)

    cli, root, keep, configure, starts = fake
    text = "Ж" * (size // 2) + (" " if size % 2 else "")
    configure(result_text=json.dumps({"summary": text}, ensure_ascii=False))
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    policy = GenerationPolicy("gpt-6-luna", timeout_seconds=60, allow_repair=False)
    with OperationFiles(root).open() as files:
        result = provider.generate(ContentInput(PROMPT, FullResult, policy), files, threading.Event())
    assert result.value.summary == text and len(text.encode()) == size
    assert result.logical_attempts == starts() == 1 and list(root.iterdir()) == [keep]


def test_structured_result_still_obeys_a_smaller_total_stream_budget(fake):
    cli, root, keep, configure, starts = fake
    configure(result_text=json.dumps({"summary": "Ж" * 40_000}, ensure_ascii=False))
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    policy = GenerationPolicy("gpt-6-luna", timeout_seconds=60, max_total_output_bytes=32 * 1024,
        allow_repair=False)
    with pytest.raises(ContentFailure, match="OUTPUT_TOO_LARGE"):
        with OperationFiles(root).open() as files:
            provider.generate(ContentInput(PROMPT, Summary, policy), files, threading.Event())
    assert starts() == 1 and list(root.iterdir()) == [keep]


def test_deadline_stops_hung_child(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("hang")
    ready = cli.parent / "ready"

    def clock():
        # Time jumps past the deadline once the fake reports that it hangs.
        return time.monotonic() + (60 if ready.exists() else 0)

    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli), clock=clock)
    with pytest.raises(ContentFailure, match="DEADLINE_EXCEEDED"):
        with OperationFiles(root).open() as files:
            provider.generate(request(timeout=30), files, threading.Event())
    assert starts() == 1 and list(root.iterdir()) == [keep]


def test_cleanup_failure_blocks_repair_and_preserves_owner_evidence(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("schema")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    from resume_api import lifecycle

    original = lifecycle.stop_group
    calls = 0

    def fail_generation_cleanup(process) -> None:
        nonlocal calls
        calls += 1
        original(process)
        # Version, help, features, login status and model list come first; the sixth is generation.
        if calls == 6:
            raise SpikeError("PROCESS_CLEANUP_FAILED")

    with patch.object(lifecycle, "stop_group", fail_generation_cleanup):
        with pytest.raises(SpikeError, match="PROCESS_CLEANUP_FAILED"):
            with OperationFiles(root).open() as files:
                with pytest.raises(ContentFailure, match="PROCESS_CLEANUP_FAILED"):
                    provider.generate(request(), files, threading.Event())
    assert starts() == 1
    assert has_blocked_owned(root)
    assert keep.read_text() == "keep"


@contextmanager
def generating(provider, root, cancel, marker):
    """Run one generation in a thread until the fake writes `marker`; always cancel and join, so a failed case cannot
    keep the process-wide generation lock for the next one."""
    errors: list[Exception] = []

    def run() -> None:
        try:
            with OperationFiles(root).open() as files:
                provider.generate(request(), files, cancel)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        # An upper bound for a real child process to start, not a timing assumption.
        end = time.monotonic() + 15
        while not marker.exists() and thread.is_alive() and time.monotonic() < end:
            time.sleep(0.01)
        assert marker.exists()
        yield errors
    finally:
        cancel.set()
        thread.join(15)
    assert not thread.is_alive()


def test_inflight_cancel_kills_descendants_and_cleans(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("tree")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with generating(provider, root, threading.Event(), cli.parent / "child_ready") as errors:
        pass
    assert len(errors) == 1 and isinstance(errors[0], ContentFailure)
    assert errors[0].code == "CANCELLED"
    assert starts() == 1 and list(root.iterdir()) == [keep]


def test_cancel_after_completion_keeps_usage_while_another_instance_runs_beside_it(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("late")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    second = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with generating(provider, root, threading.Event(), cli.parent / "ready") as errors:
        # D120: a model call no longer waits for another one on the same profile.
        configure("valid")
        with OperationFiles(root).open() as files:
            result = second.generate(request(), files, threading.Event())
        assert result.logical_attempts == 1 and starts() == 2
    assert len(errors) == 1 and isinstance(errors[0], ContentFailure)
    assert errors[0].code == "CANCELLED"
    assert errors[0].usage.input_tokens == 100 and errors[0].usage.complete
    assert list(root.iterdir()) == [keep]


def test_terminal_failure_releases_generation_for_another_instance(fake) -> None:
    cli, root, keep, configure, starts = fake
    first = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    second = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    configure("nonzero")
    with pytest.raises(ContentFailure, match="CLI_FAILED"):
        with OperationFiles(root).open() as files:
            first.generate(request(), files, threading.Event())
    configure("valid")
    with OperationFiles(root).open() as files:
        result = second.generate(request(), files, threading.Event())
    assert result.logical_attempts == 1 and starts() == 2
    assert list(root.iterdir()) == [keep]


@pytest.mark.parametrize("reply", ["A short plain reply.", "Обычный текст 🚀\n\nВторой абзац."])
def test_plain_rewrite_uses_stdin_without_schema_and_passes_selected_reasoning(fake, reply):
    from packages.resume_core.text_rewrite import PlainTextReply
    cli, root, keep, configure, starts = fake
    configure(plain_text=True, result_text=reply)
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    request = ContentInput(PROMPT, PlainTextReply,
        GenerationPolicy(model="gpt-6-luna", reasoning_effort="low", allow_repair=False))
    for _ in range(2):
        with OperationFiles(root).open() as files:
            result = provider.generate(request, files, threading.Event())
        assert result.value.text == reply and result.logical_attempts == 1
    rows = [json.loads(line) for line in (cli.parent / "audit.jsonl").read_text().splitlines()]
    generations = [row for row in rows if row.get("generation")]
    assert starts() == len(generations) == 2
    for row in generations:
        assert "--output-schema" not in row["args"]
        assert 'model_reasoning_effort="low"' in row["args"]
    assert len([row for row in rows if row.get("args", [None])[0] == "app-server"]) == 1
    assert list(root.iterdir()) == [keep]


def test_plain_rewrite_rejects_unsupported_effort_before_generation(fake):
    from packages.resume_core.text_rewrite import PlainTextReply
    cli, root, _, configure, starts = fake
    configure(plain_text=True, result_text="Reply")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        with pytest.raises(ContentFailure, match="MODEL_DENIED"):
            provider.generate(ContentInput(PROMPT, PlainTextReply,
                GenerationPolicy(model="gpt-6-luna", reasoning_effort="ultra", allow_repair=False)), files, threading.Event())
    assert starts() == 0


def test_plain_empty_reply_fails_once_without_repair(fake):
    from packages.resume_core.text_rewrite import PlainTextReply
    cli, root, _, configure, starts = fake
    configure(plain_text=True, result_text="  \n")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        with pytest.raises(ContentFailure, match="INVALID_RESULT"):
            provider.generate(ContentInput(PROMPT, PlainTextReply,
                GenerationPolicy(model="gpt-6-luna", allow_repair=False)), files, threading.Event())
    assert starts() == 1
