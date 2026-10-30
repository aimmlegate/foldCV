"""MP05 gate: the bundled Generic import publishes through the Claude provider and its CLI stream, offline."""

import pytest

from packages.resume_core.template_import import cleanup_verified, spent_calls
from tests.providers.claude_relay import EFFORT, MODEL, audit, relay_import
from tests.templates.generic_fixtures import generic_import
from tests.templates.test_template_view_adapters import text

pytestmark = pytest.mark.slow


def document(workspace):
    return [text(block) for block in workspace.project.document.blocks() if block.type != "section"]


@pytest.mark.asyncio
async def test_the_generic_import_publishes_through_the_claude_cli_stream(tmp_path):
    fixture, result, directory = await relay_import(tmp_path / "claude")
    assert result.state == "published" and result.publication.state == "saved"
    assert [attempt.error_code for attempt in result.attempts if attempt.error_code] == []
    assert cleanup_verified(result) and not list((tmp_path / "claude/operations").iterdir())
    calls = audit(directory)
    generations = [args for args in calls if args[:1] == ["-p"]]
    assert len(generations) == spent_calls(result) > 20
    for args in generations:
        assert args[args.index("--model") + 1] == MODEL and args[args.index("--effort") + 1] == EFFORT
        assert args[args.index("--tools") + 1] == "" and "--json-schema" in args
    # The probe is cached after the first three blocks, which start together; nothing signs in or out.
    assert calls.count(["--version"]) <= 3 and not any(args[:1] == ["auth"] and args[1] != "status" for args in calls)

    # The relay runs three calls at once, so the projects block is outlined (D117); the scripted import must too.
    _scripted, scripted_result, scripted, _originals = await generic_import(tmp_path / "scripted", "F10", concurrency=3)
    assert spent_calls(scripted_result) == spent_calls(result)
    assert document(fixture.current()) == document(scripted)
