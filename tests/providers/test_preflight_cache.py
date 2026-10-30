"""Reuse metadata without reusing generated text or retrying a failed turn."""

from dataclasses import replace
import json
import os
import threading

import pytest

from resume_api.lifecycle import OperationFiles
from resume_api.providers import claude_cli
from resume_api.providers.codex_cli import CodexCliProvider, FixtureTransport, Probe
from resume_api.providers.content import ContentFailure
from resume_api.providers.preflight import QUALIFICATION_SECONDS, TTL_SECONDS, PreflightCache, preflight_key
from tests.providers.fixtures import fake, request


def commands(cli):
    return [row["args"] for raw in (cli.parent / "audit.jsonl").read_text().splitlines()
        if "args" in (row := json.loads(raw))]


def check(provider, root, model="gpt-6-luna"):
    with OperationFiles(root).open() as files:
        return provider.preflight(files, threading.Event(), model, deadline=provider.clock() + 10)


def test_warm_rewrites_start_each_turn_without_repeating_metadata_processes(fake):
    cli, root, keep, _configure, starts = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    for _ in range(2):
        with OperationFiles(root).open() as files:
            result = provider.generate(request(), files, threading.Event())
        assert result.logical_attempts == 1
    args = commands(cli)
    assert sum(row == ["--version"] for row in args) == 1
    assert sum(row == ["exec", "--help"] for row in args) == 1
    assert sum(row == ["login", "status"] for row in args) == 1
    assert sum(row[0] == "app-server" for row in args) == 1
    assert starts() == 2 and list(root.iterdir()) == [keep]


@pytest.mark.parametrize("change", ["expiry", "invalidate", "binary", "auth", "auth_replace", "auth_delete", "profile"])
def test_changed_cli_credentials_profile_or_expired_metadata_are_checked_again(fake, tmp_path, monkeypatch, change):
    cli, root, _keep, _configure, starts = fake
    codex = tmp_path / "codex"
    codex.mkdir()
    auth = codex / "auth.json"
    auth.write_text("synthetic credential")
    monkeypatch.setenv("CODEX_HOME", str(codex))
    now = [0.0]
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli), clock=lambda: now[0])
    check(provider, root)
    check(provider, root)
    assert sum(row == ["--version"] for row in commands(cli)) == 1
    if change == "expiry":
        now[0] = TTL_SECONDS
    elif change == "invalidate":
        provider.invalidate_preflight()
    elif change == "binary":
        cli.write_text(cli.read_text() + "\n# Synthetic replacement\n")
    elif change == "auth":
        auth.write_text("different synthetic credential")
    elif change == "auth_replace":
        replacement = codex / "replacement"
        replacement.write_bytes(auth.read_bytes())
        os.replace(replacement, auth)
    elif change == "auth_delete":
        auth.unlink()
    else:
        monkeypatch.setenv("CODEX_HOME", str(tmp_path / "other-profile"))
    check(provider, root)
    assert sum(row == ["--version"] for row in commands(cli)) == 2
    assert starts() == 0


def test_unseen_model_refreshes_catalog_and_does_not_start_a_denied_turn(fake):
    cli, root, _keep, _configure, starts = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    check(provider, root)
    with OperationFiles(root).open() as files, pytest.raises(ContentFailure, match="MODEL_DENIED"):
        provider.generate(replace(request(), policy=replace(request().policy, model="new-model")), files, threading.Event())
    assert sum(row[0] == "app-server" for row in commands(cli)) == 2 and starts() == 0
    check(provider, root)
    assert sum(row[0] == "app-server" for row in commands(cli)) == 3


def test_failed_turn_invalidates_metadata_without_a_hidden_retry(fake):
    cli, root, _keep, configure, starts = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    check(provider, root)
    configure("expired")
    with OperationFiles(root).open() as files, pytest.raises(ContentFailure, match="AUTH_REQUIRED"):
        provider.generate(request(), files, threading.Event())
    assert starts() == 1 and sum(row == ["--version"] for row in commands(cli)) == 1
    configure("valid")
    check(provider, root)
    assert sum(row == ["--version"] for row in commands(cli)) == 2 and starts() == 1


def test_cancelled_warm_request_does_not_start_or_discard_valid_metadata(fake):
    cli, root, _keep, _configure, starts = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli))
    check(provider, root)
    cancel = threading.Event()
    cancel.set()
    with OperationFiles(root).open() as files, pytest.raises(ContentFailure, match="CANCELLED"):
        provider.generate(request(), files, cancel)
    check(provider, root)
    assert sum(row == ["--version"] for row in commands(cli)) == 1 and starts() == 0


def test_invalidation_fences_inflight_checks_and_keeps_provider_caches_separate():
    first, second = PreflightCache(), PreflightCache()
    key = ("same-cli",)
    epoch, _ = first.read(key, "model")
    first.invalidate()
    first.remember(epoch, key, "stale", ("model",))
    assert first.read(key, "model")[1] is None
    epoch, _ = first.read(key, "model")
    first.remember(epoch, key, "fresh", ("model",))
    assert first.read(key, "model")[1] == "fresh"
    assert second.read(key, "model")[1] is None


def test_credential_identity_changes_when_a_missing_file_becomes_a_dangling_link(tmp_path, monkeypatch):
    cli = tmp_path / "cli"
    cli.write_text("synthetic executable")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    before = preflight_key(cli, None, None)
    (tmp_path / "auth.json").symlink_to(tmp_path / "missing")
    assert preflight_key(cli, None, None) != before


@pytest.mark.parametrize("seconds", [3600, 5])
def test_qualification_inside_a_model_call_stays_bounded_on_codex(fake, seconds):
    cli, root, *_rest = fake
    provider = CodexCliProvider(cli, fixture_transport=FixtureTransport(cli), clock=lambda: 100.0)
    reached = []

    def probe(_files, _cancel, *, deadline):
        reached.append(deadline)
        return Probe("fixture", "chatgpt", True, ())

    def list_models(_files, _cancel, *, deadline, reasoning):
        reached.append(deadline)
        return ("gpt-6-luna",)

    provider.probe, provider.list_models = probe, list_models
    with OperationFiles(root).open() as files:
        provider.preflight(files, threading.Event(), "gpt-6-luna", deadline=100.0 + seconds)
    assert reached == [100.0 + min(seconds, QUALIFICATION_SECONDS)] * 2


@pytest.mark.parametrize("seconds", [3600, 5])
def test_qualification_inside_a_model_call_stays_bounded_on_claude(fake, seconds):
    cli, root, *_rest = fake
    provider = claude_cli.ClaudeCliProvider(cli, fixture_transport=claude_cli.FixtureTransport(cli), clock=lambda: 100.0)
    reached = []

    def probe(_files, _cancel, *, deadline):
        reached.append(deadline)
        return claude_cli.Probe("2.1.308", "supported", "claude.ai", None, True, {"claude-sonnet-5-5": None})

    provider.probe = probe
    with OperationFiles(root).open() as files:
        provider.preflight(files, threading.Event(), "claude-sonnet-5-5", deadline=100.0 + seconds)
    assert reached == [100.0 + min(seconds, QUALIFICATION_SECONDS)]
