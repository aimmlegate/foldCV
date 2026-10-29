"""An import runs beside an assistant turn on the shared inference admission (D121, permit lifecycle)."""

import asyncio
from pathlib import Path

import pytest

from resume_api.importer.template_transport import ProviderTemplateTransport
from resume_api.inference_admission import INFERENCE
from resume_api.projects.imports import ImportCommand, ImportService
from resume_api.projects.service import ProjectService
from resume_api.providers.codex_cli import CodexCliProvider
from tests.templates.template_runtime_fixtures import RuntimeFixture


@pytest.mark.asyncio
async def test_an_import_finishes_while_an_assistant_turn_holds_its_permit(tmp_path):
    fixture = RuntimeFixture(tmp_path, fallback=False)
    controlled = fixture.transport
    provider = CodexCliProvider(Path('/nonexistent/synthetic-cli'))
    provider._generate = lambda request, _files, cancel: controlled.generate(request, cancel)
    fixture.pipeline.transport = ProviderTemplateTransport(lambda: (provider, fixture.command.capture.primary.model),
        tmp_path / 'transport')
    projects = ProjectService(fixture.repository)
    imports = ImportService(projects, fixture.pipeline, commands=lambda *_args: fixture.command)
    # An assistant turn holds a permit for the whole import.
    assert INFERENCE.acquire(blocking=False)
    try:
        identifier = await imports.start(fixture.project, ImportCommand(kind='start', clientRequestId='request'),
            asyncio.Event())
        await asyncio.wait_for(imports.runners[identifier], 30)
        assert INFERENCE.shared == 1
    finally:
        INFERENCE.release()
    [status] = projects.tasks.list(fixture.project)
    operation = fixture.current().project.template_operations[0]
    assert status['state'] == 'succeeded'
    assert [attempt.error_code for attempt in operation.attempts] == [None, None]
    assert operation.tasks[0].state == 'accepted' and len(controlled.calls) == 2
