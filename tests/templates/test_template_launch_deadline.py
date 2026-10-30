"""Durable launch transitions cannot carry a stale inference deadline."""

import asyncio

import pytest

from packages.resume_core.template_import import spent_calls
from resume_api.inference_admission import InferenceAdmission
from resume_api.projects.imports import ImportCommand, ImportService
from resume_api.projects.service import ProjectService
from tests.templates.template_runtime_fixtures import RuntimeFixture


def observing(original, react):
    """Launch steps save to the sidecar (S7e); both save paths are observed."""
    def update(*args, **kwargs):
        workspace = original(*args, **kwargs)
        react((workspace.project or workspace.pre_draft).template_operations[0])
        return workspace
    return update


def expire_at(pipeline, phase):
    """Pass the import limit once an attempt reaches `phase`; returns the phases seen."""
    elapsed, observed = [0.0], []
    pipeline.elapsed = lambda: elapsed[0]
    def react(operation):
        if not observed and operation.attempts and operation.attempts[-1].state == phase:
            observed.append(phase)
            elapsed[0] = 301.0
    pipeline.update, pipeline.update_operation = observing(pipeline.update, react), observing(pipeline.update_operation, react)
    return observed


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['reserved', 'dispatch_started'])
async def test_elapsed_expiry_during_durable_launch_never_enters_transport(tmp_path, phase):
    # The coordinator knows it did not call the transport, which proves nothing ran; it used to fence the import.
    fixture = RuntimeFixture(tmp_path)
    pipeline = fixture.pipeline
    observed = expire_at(pipeline, phase)
    await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    result = fixture.current().project.template_operations[0]
    assert observed == [phase] and fixture.transport.calls == []
    assert result.inference_closed and len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.error_code == 'IMPORT_PROCESSING_EXHAUSTED' and attempt.raw_return is None
    assert result.state == 'published' and result.tasks[0].state == 'source_fallback'
    assert attempt.state == 'released' and attempt.cleanup.state == 'verified'
    assert spent_calls(result) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['reserved', 'dispatch_started'])
async def test_an_import_out_of_time_before_launch_frees_its_permit_and_publishes(tmp_path, phase):
    fixture = RuntimeFixture(tmp_path)
    expire_at(fixture.pipeline, phase)
    admission = InferenceAdmission()
    projects = ProjectService(fixture.repository)
    projects.imports = ImportService(projects, fixture.pipeline, commands=lambda *_args: fixture.command, admission=admission)
    identifier = await projects.imports.start(fixture.project, ImportCommand(kind='start', clientRequestId='request'), asyncio.Event())
    await projects.imports.runners[identifier]
    status = projects.tasks.list(fixture.project)[0]
    assert (status['state'], status['error']) == ('succeeded', None)
    assert fixture.current().project.template_operations[0].state == 'published'
    assert not admission.locked() and projects.imports.retained == {}


@pytest.mark.asyncio
async def test_transport_timeout_is_refreshed_after_durable_dispatch(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    elapsed, timeouts = [0.0], []
    pipeline = fixture.pipeline
    pipeline.elapsed = lambda: elapsed[0]
    original_generate = fixture.transport.generate
    def react(operation):
        if operation.attempts and operation.attempts[-1].state == 'dispatch_started':
            elapsed[0] = 299.0
    def generate(request, cancel):
        timeouts.append(request.policy.timeout_seconds)
        return original_generate(request, cancel)
    pipeline.update, pipeline.update_operation = observing(pipeline.update, react), observing(pipeline.update_operation, react)
    fixture.transport.generate = generate
    await pipeline.run(fixture.project, fixture.command, admitted=fixture.admitted)
    assert timeouts == [1.0, 1.0] and fixture.current().project is not None
