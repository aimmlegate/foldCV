"""CT06-S5 internal QA and manual Word matrix inputs for the Generic 2.0.0 package.

Renders the scripted F10 import and the long F07 content to DOCX, converts them with the pinned local converter only to
make pages inspectable (internal QA, not a Word result), and writes the artifacts plus an expected order and style list
for each manual Word case W01-W06.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'services/api/src'))

STYLES = {'name': 'Source Sans Pro Black 18 pt', 'profession': 'Source Sans Pro Semibold 16 pt',
    'section': 'Source Sans Pro Bold 14 pt', 'project': 'Source Sans Pro Semibold 12 pt', 'body': 'Source Sans Pro Light 10 pt'}


def render(workspace, work):
    from packages.resume_core.models.template_render import TemplateRenderRequestV1
    from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
    from packages.resume_core.storage import private_directory
    from packages.resume_core.template_export import capture_export, snapshot_identity
    private_directory(work)
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=workspace.project.template_package)
    return render_captured_docx(request, work)


def inspect(root, name, content, markers):
    import pymupdf
    from packages.resume_core.storage import atomic_write
    from tests.templates.test_captured_docx import emitted, xml
    target = root / (name + '.docx')
    atomic_write(target, content)
    result = subprocess.run([str(ROOT / '.tools/LibreOffice.app/Contents/MacOS/soffice'), '-env:UserInstallation=' + (root / 'profile').as_uri(),
        '--headless', '--convert-to', 'pdf', '--outdir', str(root), str(target)], capture_output=True, text=True, timeout=180)
    pdf = root / (name + '.pdf')
    if result.returncode or not pdf.is_file():
        raise SystemExit('QA_CONVERSION_FAILED')
    pages, text = [], ''
    with pymupdf.open(pdf) as rendered:
        for index, page in enumerate(rendered):
            spans = [span for block in page.get_text('dict')['blocks'] if block['type'] == 0 for line in block['lines'] for span in line['spans']]
            text += page.get_text()
            if index in {0, 1, len(rendered) - 1}:
                page.get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25)).save(root / f'{name}-page-{index + 1}.png')
            pages.append({'page': index + 1, 'footer': 'mail@example.com' in page.get_text(),
                'markers': sum(page.get_text().count(marker.split(':')[0]) for marker in markers),
                'textOutsidePage': [span['text'][:40] for span in spans if not page.rect.contains(pymupdf.Rect(span['bbox']))]})
    body, flat = emitted(xml(content)), ' '.join(text.split())
    return {'docx': {'path': target.name, 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
            'markersOnce': all(body.count(marker) == 1 for marker in markers), 'markerCount': len(markers),
            'inOrder': [body.index(marker) for marker in markers] == sorted(body.index(marker) for marker in markers)},
        'pdf': {'path': pdf.name, 'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(), 'pages': len(pages),
            # Marker ids prove presence; a full line can miss only when a page break splits it (the extraction then
            # interleaves the footer and the other column).
            'markerIdsFound': sum(1 for marker in markers if marker.split(':')[0] in flat),
            'wholeLinesFound': sum(1 for marker in markers if ' '.join(marker.split()) in flat),
            'footerOnEveryPage': all(page['footer'] for page in pages), 'firstPageMarkers': pages[0]['markers'],
            'textOutsidePage': sum(len(page['textOutsidePage']) for page in pages)}}


async def build(root):
    from packages.resume_core.storage import private_directory
    from tests.templates.generic_fixtures import TABLES, direct_generic, generic_import
    from tests.templates.storage_fixtures import source_fixture
    private_directory(root)
    imported = root / 'f10-import'
    _fixture, result, f10, _originals = await generic_import(imported, 'F10')
    if result.state != 'published':
        raise SystemExit('F10_IMPORT_NOT_PUBLISHED')
    f07, _sources = direct_generic('F07', ['identity', 'projects', 'courses', 'portfolio'])
    # The same long content with a Focus row opening the sidebar: a keep chain right after the first heading.
    focused = {**TABLES['F07'](True), 'focus': ([{'technology': 'Distributed Systems', 'experience': None}], {})}
    f07_focus, _sources = direct_generic('F07', ['identity', 'focus', 'projects', 'courses', 'portfolio'], table=focused)
    f10_lines = [line for line in source_fixture('F10')[0].units[0].text.splitlines() if line]
    f07_lines = source_fixture('F07')[0].units[0].text.splitlines()
    projects = [line for line in f07_lines if line.startswith('PROJECT-MARKER-')]
    sidebar = [line for line in f07_lines if line.startswith('SIDEBAR-MARKER-')]
    # Expected order from the fixture sources, written independently of the renderer.
    f10_expected = ['Example Institute', 'Example Academy', 'Example City', 'English', 'Queue Tools',
        'Backend engineer focused on reliable queue systems.', 'Example Labs', 'Queue Platform', 'Implemented queue processing.',
        'Reduced median latency by 80%.', 'Old Systems', 'Mentored five engineers across teams.', 'СУБД, ИНСТРУМЕНТЫ',
        'ИНФРАСТРУКТУРА, ТАСК-МЕНЕДЖЕРЫ']
    report = {'schemaVersion': 1, 'converter': 'pinned local LibreOffice, isolated profile; internal QA only, not Word',
        'f10': inspect(root, 'generic-f10', render(f10, root / 'work-f10'), f10_expected),
        'f07': inspect(root, 'generic-f07', render(f07, root / 'work-f07'), [*sidebar, *projects]),
        'f07Focus': inspect(root, 'generic-f07-focus', render(f07_focus, root / 'work-f07-focus'), [*sidebar, *projects])}
    matrix = {'schemaVersion': 1, 'gate': 'G04', 'status': 'pending: manual Word macOS run', 'template': {
            'id': f10.project.template_package.id, 'revision': f10.project.template_package.revision,
            'packageHash': f10.project.template_package.package_hash},
        'record': 'For each case record the Word version, the artifact hash, the observed font faces and pass or fail per condition.',
        'cases': [
            {'id': 'W01', 'artifact': 'generic-f10.docx', 'sha256': report['f10']['docx']['sha256'],
                'expectedOrder': f10_expected, 'expectedStyles': STYLES,
                'check': 'Each listed text once and in this order; text editable; sidebar and main columns as configured.'},
            {'id': 'W02', 'artifact': 'generic-f07.docx', 'sha256': report['f07']['docx']['sha256'],
                'expectedOrder': f07_lines[:2], 'check': 'Long name and title in the header; body starts below it; no overlap with '
                'the logo or divider; no truncation or font shrinking.'},
            {'id': 'W03', 'artifact': 'generic-f07.docx', 'sha256': report['f07']['docx']['sha256'],
                'expectedOrder': sidebar, 'check': 'All 100 sidebar markers once and in order across pages; no clipping or overlap '
                'with the main column or footer.'},
            {'id': 'W04', 'artifact': 'generic-f07.docx', 'sha256': report['f07']['docx']['sha256'],
                'expectedOrder': projects, 'check': 'All 250 project markers once and in order; the project splits readably; '
                'the ПРОЕКТЫ heading stays with the following text.'},
            {'id': 'W05', 'artifact': 'generic-f07.docx and generic-f10.docx', 'expectedTexts': [f07_lines[-1], 'ПРОЕКТЫ', 'СЕРТИФИКАТЫ'],
                'check': 'The long URL is clickable with its exact target and wraps; Cyrillic headings visible; the footer '
                'mail@example.com on every page; packaged Source Sans Pro faces used (no substitution).'},
            {'id': 'W06', 'artifact': 'generic-f10.docx', 'sha256': report['f10']['docx']['sha256'],
                'check': 'Edit a task line and the Queue Tools link target in Word, save, reopen: edits and the target persist; '
                'no broken layout, missing assets or overlap.'}]}
    (root / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    (root / 'word-matrix.json').write_text(json.dumps(matrix, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    root = parser.parse_args().output.resolve()
    if root.exists():
        raise SystemExit('a new output directory is required')
    asyncio.run(build(root))


if __name__ == '__main__':
    main()
