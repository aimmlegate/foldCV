"""V02: long employment wording reaches the actual captured DOCX whole, once and in order."""

from packages.resume_core.models.template_render import TemplateRenderRequestV1
from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
from packages.resume_core.template_export import capture_export, snapshot_identity
from tests.templates.long_employment_fixtures import long_lines, long_workspace
from tests.templates.test_captured_docx import emitted, xml


def test_two_hundred_fifty_long_tasks_are_emitted_once_in_order_without_truncation(tmp_path):
    workspace, _sources = long_workspace()
    project = workspace.project
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=project.template_package)
    text = emitted(xml(render_captured_docx(request, tmp_path)))
    markers = long_lines(project.sources[0])
    assert len(markers) == 250
    assert all(text.count(marker) == 1 for marker in markers)
    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert 'Check source' not in text
