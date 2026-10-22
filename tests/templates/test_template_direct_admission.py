"""Direct processing releases its shared permit before application publication."""

import pytest

from tests.templates.template_runtime_fixtures import RuntimeFixture
from resume_api.importer.template_direct import TemplateDirect
from resume_api.inference_admission import InferenceAdmission


@pytest.mark.asyncio
async def test_direct_import_owns_inference_then_releases_before_finalization(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    admission = InferenceAdmission()
    direct = TemplateDirect(fixture.pipeline, admission)
    generated, finalized = [], []
    original = fixture.transport.generate
    def generate(request, cancel):
        generated.append(admission.locked())
        return original(request, cancel)
    fixture.transport.generate = generate
    def observe(name, project):
        if name == 'before_commit_claim':
            intents = fixture.jobs.load(project).manual_intents
            if intents and intents[-1].template_finalization is not None:
                finalized.append(admission.locked())
    fixture.publisher.observer = observe
    result = await direct.run(fixture.project, fixture.command)
    assert result.state == 'published' and generated == [True, True] and finalized == [False]
    assert not admission.locked() and not direct.permits


@pytest.mark.asyncio
async def test_direct_unknown_cleanup_keeps_admission_owned(tmp_path):
    fixture = RuntimeFixture(tmp_path)
    fixture.transport.cleanup_unknown = True
    admission = InferenceAdmission()
    direct = TemplateDirect(fixture.pipeline, admission)
    result = await direct.run(fixture.project, fixture.command)
    assert result.state == 'fenced' and admission.locked() and len(fixture.transport.calls) == 1
    assert fixture.current().project is None and fixture.project in direct.permits
