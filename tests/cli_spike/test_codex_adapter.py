"""T08 fake-process contract. No live provider is invoked."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from resume_api.lifecycle import OperationFiles, SpikeError, has_blocked_owned
from resume_api.providers.codex_cli import CodexCliProvider, FixtureTransport, strict_json
from resume_api.providers.content import ContentFailure, ContentInput, GenerationPolicy


PROMPT = "Synthetic Alex; 'quotes' ☃ $() `inert` synthetic-secret"
SOURCE = Path(__file__).parent


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str = Field(min_length=1, max_length=400)


class Heading(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    heading: str = Field(min_length=1, max_length=80)


@pytest.fixture
def fake(tmp_path: Path):
    directory = tmp_path / "fake CLI 'quoted' Юникод $(inert)"
    directory.mkdir()
    cli = directory / "codex fixture"
    cli.write_text("#!" + sys.executable + "\n" + (SOURCE / "fake_cli.py").read_text().split("\n", 1)[1])
    cli.chmod(0o700)
    shutil.copyfile(SOURCE / "fixtures/success.jsonl", directory / "success.jsonl")
    root = tmp_path / "operations with spaces ' ☃ $()"
    root.mkdir()
    keep = root / "unrelated.txt"
    keep.write_text("keep")

    def configure(case: str = "valid", **extra: object) -> None:
        (directory / "fixture.json").write_text(json.dumps({"case": case, "prompt": PROMPT, **extra}))

    def starts() -> int:
        audit = directory / "audit.jsonl"
        return sum(json.loads(line).get("generation", False) for line in audit.read_text().splitlines()) if audit.exists() else 0

    configure()
    return cli, root, keep, configure, starts


def request(*, timeout: float = 3, max_total_input_bytes: int = 16_384) -> ContentInput[Summary]:
    return ContentInput(PROMPT, Summary, GenerationPolicy("gpt-6-luna", timeout_seconds=timeout,
                                                        max_total_input_bytes=max_total_input_bytes))


def test_encoded_transport_size_is_bounded_before_cli_dispatch(fake):
    from dataclasses import replace

    class Oversized:
        def encode(self, _text):
            return "x" * 65_537

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


@pytest.mark.parametrize("operation", ["normalize", "draft"])
@pytest.mark.parametrize("elapsed", [31, 61, 179, 181])
def test_gui_creation_waits_past_thirty_seconds_but_keeps_bounded_deadline(fake, monkeypatch, operation, elapsed) -> None:
    from packages.resume_core.gui_drafting import drafting_input
    from resume_api.gui_drafting_content import GuiDraftingContentService
    from resume_api.gui_normalization_content import GuiNormalizationContentService
    from tests.recovery.candidate_fixtures import ROOT, request as normalize_request, proposal
    from tests.recovery.draft_fixtures import RULES, draft_request, draft_reply

    if operation == "normalize":
        from packages.resume_core.gui_normalization import normalization_input
        from resume_api.gui_native_transport import NativeNormalizationTransport
        content_request = normalize_request((ROOT / "E1.txt").read_text())
        reply = proposal(content_request)
        prompt = NativeNormalizationTransport(content_request, RULES).encode(normalization_input(content_request, RULES))
        service_type = GuiNormalizationContentService
    else:
        from resume_api.gui_drafting_transport import DraftingTransport
        content_request = draft_request()
        reply = draft_reply(content_request)
        prompt = DraftingTransport(content_request).encode(drafting_input(content_request, RULES))
        service_type = GuiDraftingContentService
    cli, root, keep, configure, starts = fake
    configure("valid", prompt=prompt, result_text=reply.model_dump_json(by_alias=True),
              schema_required=type(reply).model_json_schema()["required"])
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
    with OperationFiles(root).open() as files:
        service = service_type(provider, "gpt-6-luna")
        if elapsed < 180:
            result, usage = service.run(content_request, RULES, files, threading.Event())
            candidate = result.candidate if operation == "normalize" else result.document.candidate
            assert candidate.name.text == "Ирина Примерова"
            assert usage["logicalAttempts"] == 1 and usage["inputTokens"] == 100
        else:
            with pytest.raises(ContentFailure) as raised:
                service.run(content_request, RULES, files, threading.Event())
            assert raised.value.code == "DEADLINE_EXCEEDED"
            assert raised.value.logical_attempts == 1
    assert starts() == 1 and list(root.iterdir()) == [keep]


def test_output_contract_is_code_owned_and_generic(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("valid", schema_required=["heading"], result_text='{"heading":"Synthetic heading"}')
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        result = provider.generate(ContentInput(PROMPT, Heading, GenerationPolicy("gpt-6-luna", timeout_seconds=3)),
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
    policy = GenerationPolicy("gpt-6-luna", timeout_seconds=3, max_total_output_bytes=500)
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
            (ContentInput("☃" * 22_000, Summary, GenerationPolicy("gpt-6-luna")), "INPUT_TOO_LARGE"),
            (ContentInput(PROMPT, Summary, GenerationPolicy("--unsafe")), "MODEL_DENIED"),
            (ContentInput(PROMPT, Loose, GenerationPolicy("gpt-6-luna")), "INVALID_SCHEMA"),
        ]:
            with pytest.raises(ContentFailure, match=code):
                provider.generate(candidate, files, threading.Event())
    assert starts() == 0 and list(root.iterdir()) == [keep]


def test_deadline_stops_hung_child(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("hang")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with pytest.raises(ContentFailure, match="DEADLINE_EXCEEDED"):
        with OperationFiles(root).open() as files:
            provider.generate(request(timeout=2.5), files, threading.Event())
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
        if calls == 5:
            raise SpikeError("PROCESS_CLEANUP_FAILED")

    with patch.object(lifecycle, "stop_group", fail_generation_cleanup):
        with pytest.raises(SpikeError, match="PROCESS_CLEANUP_FAILED"):
            with OperationFiles(root).open() as files:
                with pytest.raises(ContentFailure, match="PROCESS_CLEANUP_FAILED"):
                    provider.generate(request(), files, threading.Event())
    assert starts() == 1
    assert has_blocked_owned(root)
    assert keep.read_text() == "keep"


def test_inflight_cancel_kills_descendants_and_cleans(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("tree")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    cancel = threading.Event()
    errors: list[Exception] = []

    def run() -> None:
        try:
            with OperationFiles(root).open() as files:
                provider.generate(request(timeout=3), files, cancel)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    ready = cli.parent / "child_ready"
    end = time.monotonic() + 2
    while not ready.exists() and time.monotonic() < end:
        time.sleep(0.01)
    assert ready.exists()
    cancel.set()
    thread.join(3)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], ContentFailure)
    assert errors[0].code == "CANCELLED"
    assert starts() == 1 and list(root.iterdir()) == [keep]


def test_cancel_after_completion_keeps_usage_and_blocks_parallel_instances(fake) -> None:
    cli, root, keep, configure, starts = fake
    configure("late")
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    second = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    cancel = threading.Event()
    errors: list[Exception] = []

    def run() -> None:
        try:
            with OperationFiles(root).open() as files:
                provider.generate(request(timeout=3), files, cancel)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    ready = cli.parent / "ready"
    end = time.monotonic() + 2
    while not ready.exists() and time.monotonic() < end:
        time.sleep(0.01)
    assert ready.exists()
    with pytest.raises(ContentFailure, match="BUSY") as busy:
        with OperationFiles(root).open() as files:
            second.generate(request(), files, threading.Event())
    assert busy.value.logical_attempts == 0
    cancel.set()
    thread.join(3)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], ContentFailure)
    assert errors[0].code == "CANCELLED"
    assert errors[0].usage.input_tokens == 100 and errors[0].usage.complete
    assert starts() == 1 and list(root.iterdir()) == [keep]
    configure("valid")
    with OperationFiles(root).open() as files:
        result = second.generate(request(), files, threading.Event())
    assert result.logical_attempts == 1 and starts() == 2
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
