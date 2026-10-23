"""CT05 V02 internal QA: the F07 employment flows across pages in the actual captured DOCX.

The product exports DOCX without a converter; the pinned local converter here only makes pages inspectable.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'services/api/src'))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    root = parser.parse_args().output.resolve()
    if root.exists():
        raise SystemExit('a new output directory is required')
    import pymupdf
    from packages.resume_core.models.template_render import TemplateRenderRequestV1
    from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
    from packages.resume_core.storage import atomic_write, private_directory
    from packages.resume_core.template_export import capture_export, snapshot_identity
    from tests.templates.long_employment_fixtures import long_lines, long_workspace
    from tests.templates.test_captured_docx import emitted, xml
    private_directory(root)
    workspace, sources = long_workspace()
    project = workspace.project
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=project.template_package)
    work = root / 'work'; private_directory(work)
    content = render_captured_docx(request, work)
    target = root / 'long-employment.docx'; atomic_write(target, content)
    markers = long_lines(next(iter([source for source in project.sources])))
    docx_text = emitted(xml(content))
    result = subprocess.run([str(ROOT / '.tools/LibreOffice.app/Contents/MacOS/soffice'), '-env:UserInstallation=' + (root / 'profile').as_uri(),
        '--headless', '--convert-to', 'pdf', '--outdir', str(root), str(target)], capture_output=True, text=True, timeout=120)
    pdf = root / 'long-employment.pdf'
    if result.returncode or not pdf.is_file():
        raise SystemExit('QA_CONVERSION_FAILED')
    pages, text = [], ''
    with pymupdf.open(pdf) as rendered:
        for index, page in enumerate(rendered):
            spans = [span for block in page.get_text('dict')['blocks'] if block['type'] == 0 for line in block['lines'] for span in line['spans']]
            text += page.get_text()
            if index in {0, 1, len(rendered) - 1}:
                png = root / f'page-{index + 1}.png'; page.get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25)).save(png)
            pages.append({'page': index + 1, 'markers': sum(1 for span in spans if 'PROJECT-MARKER-' in span['text']),
                'textOutsidePage': [span['text'][:40] for span in spans if not page.rect.contains(pymupdf.Rect(span['bbox']))]})
    flat = ' '.join(text.split())
    report = {'schemaVersion': 1, 'case': 'V02 employment subset (F07 project wording, 250 tasks)',
        'sourceSha256': hashlib.sha256(sources[next(iter(sources))]).hexdigest(),
        'docx': {'path': target.name, 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
            'markersOnce': all(docx_text.count(marker) == 1 for marker in markers), 'markerCount': len(markers),
            'inOrder': [docx_text.index(marker) for marker in markers] == sorted(docx_text.index(marker) for marker in markers)},
        'pdf': {'path': pdf.name, 'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(), 'pages': len(pages),
            'markersFound': sum(1 for marker in markers if marker.split(':')[0] in flat),
            'textOutsidePage': sum(len(page['textOutsidePage']) for page in pages), 'perPage': pages},
        'converter': 'pinned local LibreOffice, isolated profile; internal QA only', 'renderer': renderer_identity().model_dump(mode='json')}
    (root / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({key: report[key] for key in ('docx', 'pdf')} | {'pdf': {k: v for k, v in report['pdf'].items() if k != 'perPage'}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
