"""MP02 fake-process contract for the Claude adapter. No live provider is invoked."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import threading

from pydantic import BaseModel, ConfigDict, Field
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.text_rewrite import PlainTextReply
from resume_api.cli import qualification
from resume_api.cli.process_runner import ProcessRunner
from resume_api.cli.profiles import claude as rules
from resume_api.connection import ConnectionFailure
from resume_api.connection_claude import ClaudeConnectionAdapter
from resume_api.lifecycle import OperationFiles
from resume_api.providers import claude_catalog
from resume_api.providers.claude_cli import ClaudeCliProvider, FixtureTransport
from resume_api.providers.content import ContentFailure, ContentInput, GenerationPolicy


PROMPT = "Synthetic Alex; 'quotes' ☃ $() `inert` synthetic-secret"
MODEL = "claude-sonnet-5-5"
SOURCE = Path(__file__).parent


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str = Field(min_length=1, max_length=400)


@pytest.fixture
def fake(tmp_path: Path):
    directory = tmp_path / "fake CLI 'quoted' Юникод $(inert)"
    directory.mkdir()
    cli = directory / "claude fixture"
    cli.write_text("#!" + sys.executable + "\n" + (SOURCE / "fake_claude.py").read_text().split("\n", 1)[1])
    cli.chmod(0o700)
    root = tmp_path / "operations ' ☃"
    root.mkdir()

    def configure(case: str = "valid", **extra: object) -> None:
        (directory / "fixture.json").write_text(json.dumps(
            {"case": case, "value": {"summary": "Synthetic summary"}, "invalid": {"summary": 7}, **extra}))
        for name in ("calls", "audit.jsonl", "signed-in"):
            (directory / name).unlink(missing_ok=True)

    def audit() -> list[dict]:
        path = directory / "audit.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    configure()
    return cli, root, directory, configure, audit


def request(*, model: str = MODEL, repair: bool = True, effort=None, result=Summary, timeout: float = 5):
    return ContentInput(PROMPT, result, GenerationPolicy(model, timeout_seconds=timeout, allow_repair=repair,
                                                         reasoning_effort=effort))


def generate(fake, case: str = "valid", value=None, **config):
    cli, root, _directory, configure, audit = fake
    configure(case, **config)
    provider = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        result = provider.generate(value or request(), files, threading.Event())
    assert list(root.iterdir()) == []
    return result, [entry for entry in audit() if entry["generation"]]


def failure(fake, case: str, code: str, starts: int, value=None, **config) -> ContentFailure:
    cli, root, _directory, configure, audit = fake
    configure(case, **config)
    provider = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with pytest.raises(ContentFailure) as raised:
        with OperationFiles(root).open() as files:
            provider.generate(value or request(), files, threading.Event())
    assert raised.value.code == code
    assert PROMPT not in str(raised.value) and "synthetic-secret" not in str(raised.value)
    assert sum(entry["generation"] for entry in audit()) == starts
    assert list(root.iterdir()) == []
    return raised.value


def test_success_uses_the_isolated_argv_and_keeps_the_prompt_on_stdin(fake):
    result, starts = generate(fake)
    assert result.value == Summary(summary="Synthetic summary")
    assert (result.cli_version, result.model, result.logical_attempts) == ("2.1.308", MODEL, 1)
    assert result.usage.input_tokens == 20 and result.usage.cached_input_tokens == 5 and result.usage.output_tokens == 7
    assert result.raw_return == '{"summary":"Synthetic summary"}' and result.cleanup_verified
    args = starts[0]["args"]
    assert len(starts) == 1 and PROMPT not in " ".join(args)
    assert (fake[2] / "prompt-1.txt").read_text() == PROMPT
    for flag in ("--restricted", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in args
    assert args[args.index("--tools") + 1] == "" and args[args.index("--permission-mode") + 1] == "dontAsk"
    assert args[args.index("--permission-prompts") + 1] == "none"
    assert json.loads(args[args.index("--settings") + 1])["disableAllHooks"] is True
    assert "--dangerously-skip-permissions" not in args and "--bare" not in args and "--effort" not in args


def test_effort_from_the_catalog_is_passed_and_unknown_effort_is_denied(fake):
    _result, starts = generate(fake, value=request(effort="max"))
    assert starts[0]["args"][starts[0]["args"].index("--effort") + 1] == "max"
    failure(fake, "valid", "MODEL_DENIED", 0, value=request(effort="minimal"))
    failure(fake, "valid", "MODEL_DENIED", 0, value=request(model="claude-unknown-9"))


def test_invalid_output_repairs_once_and_counts_both_dispatches(fake):
    result, starts = generate(fake, "repair")
    assert result.logical_attempts == 2 and len(starts) == 2
    assert (fake[2] / "prompt-2.txt").read_text().startswith(PROMPT + "\n\n")
    assert result.usage.output_tokens == 14


def test_allowed_runs_without_repair_dispatch_exactly_once(fake):
    failure(fake, "repair", "INVALID_RESULT", 1, value=request(repair=False))


def test_plain_text_drops_the_schema_and_returns_the_final_text(fake):
    result, starts = generate(fake, "valid", value=request(result=PlainTextReply), text="Rewritten line")
    assert result.value.text == "Rewritten line" and "--json-schema" not in starts[0]["args"]


def test_a_run_that_renews_the_sign_in_runs_once_more(fake):
    result, starts = generate(fake, "renewal")
    assert result.value.summary == "Synthetic summary" and len(starts) == 2 and result.logical_attempts == 2
    assert starts[0]["args"] == starts[1]["args"]


def test_a_sign_in_that_stays_refused_fails_after_the_second_run(fake):
    error = failure(fake, "auth", "AUTH_REQUIRED", 2)
    assert error.cleanup_verified


@pytest.mark.parametrize(("case", "code"), [
    ("rate_limit", "RATE_LIMITED"), ("quota", "QUOTA_EXHAUSTED"),
    ("model", "MODEL_DENIED"), ("billing", "QUOTA_EXHAUSTED"), ("max_retries", "INVALID_RESULT"),
    ("tool", "UNEXPECTED_TOOL_ACTIVITY"), ("subagent", "UNEXPECTED_TOOL_ACTIVITY"),
    ("compact", "UNEXPECTED_TOOL_ACTIVITY"), ("denied", "UNEXPECTED_TOOL_ACTIVITY"),
    ("init_mcp", "CLI_PROFILE_UNSAFE"), ("init_model", "CLI_PROFILE_UNSAFE"),
    ("init_plugin", "CLI_PROFILE_UNSAFE"), ("init_key", "CLI_PROFILE_UNSAFE"),
    ("bad_schema", "INVALID_SCHEMA"), ("unknown_option", "CLI_PROFILE_UNSAFE"),
    ("incomplete", "INCOMPLETE_STREAM"), ("unknown_notice", "INVALID_RESULT"),
])
def test_failures_are_typed_without_a_second_dispatch(fake, case, code):
    error = failure(fake, case, code, 1)
    assert error.logical_attempts == 1 and error.cleanup_verified


def test_an_unknown_notice_is_named_in_the_log_without_its_content(fake, caplog):
    failure(fake, "unknown_notice", "INVALID_RESULT", 1)
    assert [record.getMessage() for record in caplog.records] == ["Claude stream event refused: system/new_notice"]


class Open(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str


def generate_open(fake, case="valid", **config):
    cli, root, _directory, configure, _audit = fake
    configure(case, **config)
    provider = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        return provider.generate(request(result=Open), files, threading.Event())


def test_a_reply_above_half_the_budget_fits_though_the_stream_carries_it_twice(fake, monkeypatch):
    limits = {}
    run = ProcessRunner.run

    def spy(self, *args, **options):
        limits.update(options)
        return run(self, *args, **options)

    monkeypatch.setattr(ProcessRunner, "run", spy)
    assert generate_open(fake, value={"summary": "x" * 140_000}).value.summary == "x" * 140_000
    assert limits["max_line"] == 262_144 and limits["max_output"] == 8 * 262_144


def test_a_repair_after_a_long_invalid_reply_counts_only_its_final_line(fake):
    result = generate_open(fake, "repair", value={"summary": "x" * 100_000},
                           invalid={"summary": "x" * 100_000, "extra": 1})
    assert result.value.summary == "x" * 100_000 and result.logical_attempts == 2


def test_a_reply_above_the_final_limit_is_still_too_large(fake):
    with pytest.raises(ContentFailure) as raised:
        generate_open(fake, value={"summary": "x" * 270_000})
    assert raised.value.code == "OUTPUT_TOO_LARGE"


def test_missing_structured_output_is_repaired_like_invalid_json(fake):
    failure(fake, "no_output", "INVALID_RESULT", 2)


def test_retry_notice_is_tolerated(fake):
    result, _starts = generate(fake, "retry")
    assert result.value.summary == "Synthetic summary"


@pytest.mark.parametrize(("case", "code", "extra"), [
    ("logged_out", "AUTH_REQUIRED", {}), ("api_key", "AUTH_MODE_MISMATCH", {}),
    ("bad_help", "CLI_PROFILE_UNSAFE", {}), ("valid", "CLI_UNSUPPORTED", {"version": "2.1.290 (Claude Code)"}),
    ("valid", "CLI_UNSUPPORTED", {"version": "not a version"}),
])
def test_preflight_fails_before_any_dispatch(fake, case, code, extra):
    failure(fake, case, code, 0, **extra)


def test_newer_untested_version_is_graceful_and_still_generates(fake):
    cli, root, _directory, configure, _audit = fake
    configure("valid", version="2.2.0 (Claude Code)")
    provider = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        probe = provider.probe(files, threading.Event())
    assert probe.status == "graceful" and probe.plan == "max" and MODEL in probe.reasoning


def test_preflight_is_reused_until_invalidated(fake):
    cli, root, _directory, configure, audit = fake
    provider = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli))
    for _ in range(2):
        with OperationFiles(root).open() as files:
            provider.generate(request(), files, threading.Event())
    assert sum(entry["args"] == ["auth", "status", "--json"] for entry in audit()) == 1
    provider.invalidate_preflight()
    with OperationFiles(root).open() as files:
        provider.generate(request(), files, threading.Event())
    assert sum(entry["args"] == ["auth", "status", "--json"] for entry in audit()) == 2


def test_timeout_and_cancel_stop_the_process_group(fake):
    cli, root, directory, configure, _audit = fake
    configure("hang")
    provider = ClaudeCliProvider(cli, fixture_transport=FixtureTransport(cli))
    with pytest.raises(ContentFailure) as raised:
        with OperationFiles(root).open() as files:
            provider.generate(request(timeout=1.5), files, threading.Event())
    assert raised.value.code == "DEADLINE_EXCEEDED" and raised.value.cleanup_verified
    cancel = threading.Event()
    threading.Timer(0.8, cancel.set).start()
    with pytest.raises(ContentFailure) as raised:
        with OperationFiles(root).open() as files:
            provider.generate(request(timeout=10), files, cancel)
    assert raised.value.code == "CANCELLED" and raised.value.cleanup_verified
    assert list(root.iterdir()) == []


def test_production_mode_requires_a_profile(fake):
    cli, root, _directory, _configure, audit = fake
    provider = ClaudeCliProvider(cli)
    with pytest.raises(ContentFailure) as raised:
        with OperationFiles(root).open() as files:
            provider.generate(request(), files, threading.Event())
    assert raised.value.code == "CLI_PROFILE_UNSAFE" and audit() == []


def test_unsigned_binary_is_unsupported(fake, tmp_path):
    cli, root, _directory, _configure, audit = fake
    profile = rules.ClaudeCliProfile(tmp_path / "profile", cli, home=tmp_path / "home")
    provider = ClaudeCliProvider(cli, profile=profile)
    with pytest.raises(ContentFailure) as raised:
        with OperationFiles(root).open() as files:
            provider.generate(request(), files, threading.Event())
    assert raised.value.code == "CLI_UNSUPPORTED" and audit() == []


def test_connection_reports_catalog_plan_and_no_quota_source(fake):
    cli, root, _directory, _configure, audit = fake
    adapter = ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        metadata = adapter.inspect(files, threading.Event())
    assert metadata.version == "2.1.308" and metadata.plan == "max" and metadata.quota.state == "not_provided"
    assert set(metadata.models) == {model.id for model in claude_catalog.MODELS}
    assert metadata.reasoning[MODEL].default == "high"
    assert not any(entry["generation"] for entry in audit())


@pytest.mark.parametrize(("case", "code", "extra", "version"), [
    ("logged_out", "LOGIN_REQUIRED", {}, "2.1.308"), ("api_key", "API_KEY_MODE", {}, "2.1.308"),
    ("valid", "UNSUPPORTED_VERSION", {"version": "2.1.200 (Claude Code)"}, "2.1.200"),
    ("valid", "UNSUPPORTED_VERSION", {"version": "no version here"}, None),
])
def test_connection_states_name_the_version_the_cli_reported(fake, case, code, extra, version):
    cli, root, _directory, configure, _audit = fake
    configure(case, **extra)
    with pytest.raises(ConnectionFailure) as raised:
        with OperationFiles(root).open() as files:
            ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli)).inspect(files, threading.Event())
    assert raised.value.code == code and raised.value.version == version


@pytest.mark.parametrize(("subscription", "plan"), [("max", "max"), ("team_premium", "team_premium"), ("Claude Max", None),
                                                    ("x" * 41, None), (7, None), (None, None)])
def test_only_a_plan_the_client_accepts_is_reported(fake, subscription, plan):
    cli, root, _directory, configure, _audit = fake
    configure(subscription=subscription)
    with OperationFiles(root).open() as files:
        metadata = ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli)).inspect(files, threading.Event())
    assert metadata.plan == plan


def test_login_runs_the_cli_sign_in_only_when_signed_out(fake):
    cli, root, _directory, configure, audit = fake
    adapter = ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli))
    with OperationFiles(root).open() as files:
        adapter.login(files, threading.Event())
    assert ["auth", "login", "--claudeai"] not in [entry["args"] for entry in audit()]
    configure("logged_out")
    with OperationFiles(root).open() as files:
        adapter.login(files, threading.Event())
    with OperationFiles(root).open() as files:
        assert adapter.inspect(files, threading.Event()).plan == "max"
    assert [entry["args"] for entry in audit()].count(["auth", "login", "--claudeai"]) == 1
    assert ["auth", "logout"] not in [entry["args"] for entry in audit()]


def test_login_forwards_the_pasted_code_and_keeps_stdin_open_until_then(fake):
    cli, root, _directory, configure, _audit = fake
    configure("login_code")
    adapter = ClaudeConnectionAdapter(None, fixture_transport=FixtureTransport(cli))
    calls = []

    def code():
        calls.append(1)
        return "synthetic-code" if len(calls) > 3 else None

    with OperationFiles(root).open() as files:
        adapter.login(files, threading.Event(), code)
    with OperationFiles(root).open() as files:
        assert adapter.inspect(files, threading.Event(), full=False).version == "2.1.308"
    configure("login_code")
    with pytest.raises(ConnectionFailure) as raised:
        with OperationFiles(root).open() as files:
            adapter.login(files, threading.Event(), lambda: "wrong")
    assert raised.value.code == "CLI_FAILED"


# Version policy (section 5) and the profile, without processes.

@pytest.mark.parametrize(("text", "parsed"), [
    ("2.1.308 (Claude Code)", "2.1.308"), ("codex-cli 0.163.0-alpha.11.1", "0.163.0-alpha.11.1"),
    ("v1.0.67", "1.0.67"),
])
def test_versions_parse_from_cli_banners(text, parsed):
    assert str(qualification.Version.parse(text)) == parsed


def test_prerelease_ordering_and_statuses():
    parse = qualification.Version.parse
    assert parse("0.163.0-alpha.2") < parse("0.163.0-alpha.11") < parse("0.163.0-beta") < parse("0.163.0")
    table = qualification.Compatibility(floor="2.1.302", last_tested="2.1.308", broken=("2.1.305",))
    assert [table.status(parse(v)) for v in ("2.1.301", "2.1.302", "2.1.305", "2.1.308", "2.1.309")] == [
        "unsupported", "supported", "broken", "supported", "graceful"]


def test_help_flags_match_whole_words_only():
    assert qualification.missing_flags("--tools-extra  --print", ("--tools", "--print")) == ("--tools",)


def test_catalog_hides_models_newer_than_the_cli():
    old = {model.id for model in claude_catalog.models_for(qualification.Version.parse("2.1.282"))}
    assert old == {"claude-opus-5-5", "claude-fable-5-1"}
    reasoning = claude_catalog.reasoning_for(qualification.Version.parse("2.1.308"))
    assert reasoning[MODEL].default == "high" and "ultrathink" not in reasoning[MODEL].supported


def test_profile_environment_is_an_allowlist_without_key_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-secret")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "synthetic-secret")
    profile = rules.ClaudeCliProfile(tmp_path / "profile", Path("/bin/echo"), home=tmp_path)
    env = profile.environment(tmp_path / "op")
    assert not set(rules.STRIPPED) & set(env) and "synthetic-secret" not in json.dumps(env)
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "profile/claude")
    assert env["CLAUDE_CODE_TMPDIR"] == env["TMPDIR"] == str(tmp_path / "op/tmp") and env["USER"]


def test_policy_confines_files_and_processes(tmp_path):
    profile = rules.ClaudeCliProfile(tmp_path / "profile", Path("/bin/echo"), home=tmp_path)
    (tmp_path / "profile").mkdir()
    policy = profile.policy(tmp_path, ("-p",))
    assert "(deny network*)" not in policy and '"/usr/bin/open"' not in policy
    assert "(deny process-exec)" in policy and '(literal "/usr/bin/security")' in policy
    assert '(subpath "/private/var/db/timezone")' in policy
    keychains = '(subpath "' + str(tmp_path.resolve() / "Library/Keychains") + '")'
    assert policy.count(keychains) == 2 and "/Library/Application Support" not in policy
    assert "(deny network*)" in profile.policy(tmp_path, ("-p",), network=False)
    assert '"/usr/bin/open"' in profile.policy(tmp_path, ("auth", "login", "--claudeai"))


def test_prepare_refuses_the_users_own_config_and_foreign_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "mine"))
    with pytest.raises(rules.ClaudeProfileError):
        rules.ClaudeCliProfile(tmp_path / "home", Path("/bin/echo"), home=tmp_path / "home").prepare()
    with pytest.raises(rules.ClaudeProfileError):
        rules.ClaudeCliProfile(tmp_path / "mine", Path("/bin/echo"), home=tmp_path / "home").prepare()
    (tmp_path / "foreign").mkdir()
    with pytest.raises(rules.ClaudeProfileError):
        rules.ClaudeCliProfile(tmp_path / "foreign", Path("/bin/echo"), home=tmp_path / "home").prepare()


def test_every_call_of_a_profile_runs_in_one_private_working_directory(tmp_path):
    profile = rules.ClaudeCliProfile(tmp_path / "profile", Path("/bin/echo"), home=tmp_path / "home")
    provider = ClaudeCliProvider(Path("/bin/echo"), profile=profile)
    assert provider.process.workdir == profile.workdir == profile.root / "cwd"
    profile.prepare()
    assert profile.workdir.is_dir() and profile.workdir.stat().st_mode & 0o777 == 0o700
    assert profile.environment(tmp_path)["TMPDIR"] == str(tmp_path / "tmp")


def test_wipe_keeps_only_the_config_file_and_credentials(tmp_path):
    profile = rules.ClaudeCliProfile(tmp_path / "profile", Path("/bin/echo"), home=tmp_path / "home")
    profile.prepare()
    for name in (".claude.json", ".credentials.json", "history.jsonl"):
        (profile.config_dir / name).write_text("{}")
    for name in ("projects/x", "backups", "todos", "statsig"):
        (profile.config_dir / name).mkdir(parents=True)
    assert profile.wipe() == ["backups", "history.jsonl", "projects", "statsig", "todos"]
    assert sorted(path.name for path in profile.config_dir.iterdir()) == [".claude.json", ".credentials.json"]


def test_init_check_requires_the_exact_reported_session():
    event = {"type": "system", "subtype": "init", "tools": ["StructuredOutput"], "mcp_servers": [],
             "slash_commands": [], "skills": [], "plugins": [], "permissionMode": "dontAsk", "model": MODEL,
             "apiKeySource": "none", "claude_code_version": "2.1.308"}
    rules.check_init(event, model=MODEL, version="2.1.308", tools=("StructuredOutput",))
    for key, value in (("tools", ["StructuredOutput", "Read"]), ("permissionMode", "default"),
                       ("skills", ["x"]), ("claude_code_version", "2.1.309")):
        with pytest.raises(rules.ClaudeProfileError):
            rules.check_init({**event, key: value}, model=MODEL, version="2.1.308", tools=("StructuredOutput",))


def test_envelopes_of_the_live_mp00_run_are_accepted():
    from resume_api.providers.claude_cli import ClaudeEvents
    from resume_api.providers.structured_schema import StructuredSchema

    class Check(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        answer: str
        count: int
        items: list[str]

    events = ClaudeEvents(model=MODEL, version="2.1.308", structured=True, max_bytes=262_144)
    for raw in (SOURCE / "fixtures/claude-2.1.308-structured.jsonl").read_bytes().splitlines():
        events.accept(raw)
    value = events.result(Check, StructuredSchema(Check.model_json_schema()))
    assert value == Check(answer="ready", count=3, items=["alpha", "beta", "gamma"])
    assert (events.usage.input_tokens, events.usage.output_tokens, events.usage.complete) == (1230, 107, True)
