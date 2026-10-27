"""Actual isolated workers retain the existing process and cleanup owner."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from packages.resume_core.rendering.captured_docx import renderer_identity
from packages.resume_core.rendering.template import RenderFailure
from tests.templates.test_captured_docx import captured_request, emitted, xml

WORKER = Path('packages/resume_core/rendering/worker.py').resolve()


def run_worker(directory):
    return subprocess.run([sys.executable, str(WORKER)], cwd=directory, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)


def test_actual_subprocess_renders_captured_employment(captured_request, tmp_path):
    (tmp_path / 'template-docx-input.json').write_text(captured_request.model_dump_json(by_alias=True))
    process = run_worker(tmp_path)
    assert process.returncode == 0, process.stderr.decode()
    content = (tmp_path / 'resume.docx').read_bytes()
    assert 'Example Labs' in emitted(xml(content))
    assert (tmp_path / 'captured-assets').is_dir()
    assert not (tmp_path / 'render-output.zip').exists()


@pytest.mark.parametrize('damage', ['renderer', 'schema', 'input_version', 'hash', 'assets', 'ambiguous'])
def test_actual_worker_rejects_mismatched_or_ambiguous_capture(captured_request, tmp_path, damage):
    value = captured_request.model_dump(mode='json', by_alias=True)
    if damage == 'renderer':
        value['renderer']['sha256'] = '0' * 64
    elif damage == 'schema':
        value['schemaVersion'] = 2
    elif damage == 'input_version':
        value['renderInputVersion'] = 2
    elif damage == 'hash':
        value['documentHash'] = '0' * 64
    elif damage == 'assets':
        value['assets'][0]['sha256'] = '0' * 64
    else:
        (tmp_path / 'rich-docx-input.json').write_text('{}')
    (tmp_path / 'template-docx-input.json').write_text(json.dumps(value))
    process = run_worker(tmp_path)
    assert process.returncode == 1
    assert not (tmp_path / 'resume.docx').exists()
    code = json.loads((tmp_path / 'render-status.json').read_text())['code']
    assert code == ('RENDERER_MISMATCH' if damage == 'renderer' else 'RICH_EXPORT_UNSUPPORTED' if damage == 'ambiguous' else 'RENDER_FAILED')


@pytest.mark.asyncio
async def test_template_renderer_runs_actual_captured_worker_and_cleans(captured_request, tmp_path):
    from resume_api.rendering import TemplateDocxRenderer
    from resume_api.lifecycle import OperationFiles
    root = tmp_path / 'isolated-operations'
    with OperationFiles(root).open() as files:
        path = files.path
        content = await TemplateDocxRenderer().render_template(captured_request, files)
        assert files.closed and files.process is None
        assert not (path / '.worker').exists()
    assert not path.exists()
    assert 'Example Labs' in emitted(xml(content))
