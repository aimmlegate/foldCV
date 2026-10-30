"""The live assistant mode of the preview tool charges every native start and starts nothing else."""

from argparse import Namespace
import asyncio
import threading

import pytest

from resume_api.agent.runtime import RuntimeInput, RuntimeResult
from resume_api.cli.experimental_profile import ExperimentalCliProfile
from resume_api.connection import Metadata, Quota
from resume_api.projects.errors import ProjectFailure
from tests.service.app_fixtures import make_app
from tools import serve_synthetic

MODEL = "gpt-6-luna"


class FakeNative:
    starts = 0

    def __init__(self, *_args):
        pass

    async def run(self, _value, _cancel, _emit):
        type(self).starts += 1
        return RuntimeResult(state="completed", text="done")


class Connection:
    def inspect(self, _files, _cancel, *, full=True):
        return Metadata("codex-cli fixture", (MODEL,), "plus", Quota("available", 25, 1800000000))


@pytest.fixture
def live(tmp_path, monkeypatch):
    """The native branch of `create_app`: a personal profile with the Codex runtime class stubbed."""
    FakeNative.starts = 0
    monkeypatch.setattr("resume_api.app.CodexAgentRuntime", FakeNative)
    monkeypatch.setattr(serve_synthetic, "OUTCOMES", tmp_path / "outcomes.jsonl")
    app = make_app(tmp_path, connection_adapter=Connection(),
                   experimental_profile=ExperimentalCliProfile(tmp_path / "profile"))
    return app, tmp_path / "ledger.jsonl"


def start(app):
    value = RuntimeInput(model=MODEL, prompt='context\n{"message": "check"}', url="http://127.0.0.1:1/mcp", token="t",
                         tools=(), allow_web=False)
    runtime = app.app.state.assistant.runtime_for(MODEL)
    return asyncio.run(runtime.run(value, threading.Event(), lambda *_: None))


def test_a_native_run_is_charged_before_it_starts(live):
    app, ledger = live
    serve_synthetic.install_live_limits(app, ledger, 1)
    assert start(app).state == "completed"
    assert FakeNative.starts == 1 and len(ledger.read_text().splitlines()) == 1


def test_a_start_past_the_allowance_is_refused_without_a_native_start(live):
    app, ledger = live
    budget = serve_synthetic.install_live_limits(app, ledger, 0)
    assert start(app).error == "AGENT_QUOTA"
    assert FakeNative.starts == 0 and budget.calls == [] and not ledger.exists()


def test_the_allowance_counts_starts_of_earlier_service_runs(live):
    app, ledger = live
    ledger.write_text("{}\n{}\n")
    serve_synthetic.install_live_limits(app, ledger, 2)
    assert start(app).error == "AGENT_QUOTA"
    assert FakeNative.starts == 0


def test_a_model_without_a_runtime_stays_unavailable(live, tmp_path):
    app, ledger = live
    app.app.state.assistant.runtime_for = lambda _model: None
    serve_synthetic.install_live_limits(app, ledger, 1)
    assert app.app.state.assistant.runtime_for(MODEL) is None


def test_a_live_rewrite_is_refused_before_any_provider(live):
    app, ledger = live
    serve_synthetic.install_live_limits(app, ledger, 1)
    with pytest.raises(ProjectFailure) as refused:
        asyncio.run(app.app.state.projects.rewrite_text("project", "request", "shorter", "text"))
    assert refused.value.code == "CONNECTION_REQUIRED"


def test_live_mode_refuses_template_imports_before_it_makes_the_root(tmp_path):
    root = tmp_path / "root"
    args = Namespace(live_assistant=True, template_call_cap=3, root=root)
    with pytest.raises(ValueError, match="template-call-cap"):
        asyncio.run(serve_synthetic.main(args))
    assert not root.exists()
