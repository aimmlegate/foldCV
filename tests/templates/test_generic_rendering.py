"""S5: the Generic 2.0.0 package through the actual export route and captured worker (V01, V03, V04) and long content (V02)."""

import uuid

import pytest
from docx.oxml.ns import qn
from lxml import etree

from packages.resume_core.models.template_render import TemplateRenderRequestV1
from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
from packages.resume_core.template_export import capture_export, snapshot_identity
from packages.resume_core.templates.compiler import sha256
from tests.templates.generic_fixtures import direct_generic, export_through_service as exported
from tests.templates.storage_fixtures import source_fixture
from tests.templates.test_captured_docx import NS, emitted, parts, recapture, xml
from tests.templates.test_generic_import import shared, views
from tests.templates.test_template_view_adapters import text


EXPORTS = {}
F10_LINE = 'Reduced median latency by 80%.'
# W01's measured Generic faces and sizes (half-points): name, profession, section, project, body.
STYLES = {'name': ('Source Sans Pro Black', '36', '0'), 'profession': ('Source Sans Pro Semibold', '32', '0'),
    'section': ('Source Sans Pro', '28', '1'), 'project': ('Source Sans Pro Semibold', '24', '0'),
    'body': ('Source Sans Pro Light', '20', '0'), 'emphasis': ('Source Sans Pro Semibold', '20', '0')}


async def f10_export(tmp_path_factory):
    if 'F10' not in EXPORTS:
        _fixture, _result, workspace, originals = await shared(tmp_path_factory, 'F10-on')
        EXPORTS['F10'] = workspace, await exported(tmp_path_factory.mktemp('f10-export'), workspace, originals)
    return EXPORTS['F10']


def styles(tree, value):
    """(font, size, bold) of every run whose whole text is value."""
    result = []
    for run in tree.iter(qn('w:r')):
        if ''.join(node.text or '' for node in run.iter(qn('w:t'))) != value:
            continue
        props = run.find(qn('w:rPr'))
        bold = props.find(qn('w:b'))
        result.append((props.find(qn('w:rFonts')).get(qn('w:ascii')), props.find(qn('w:sz')).get(qn('w:val')),
            bold.get(qn('w:val')) if bold is not None else '0'))
    return result


def walk(blocks):
    for block in blocks:
        yield block
        yield from walk(block.children)


def body_texts(document):
    return [text(block) for region in document.regions if region.role != 'header' for block in walk(region.blocks)
        if block.type != 'section' and text(block)]


def shaded(tree):
    return [emitted(paragraph) for paragraph in tree.xpath('//w:body//w:p[w:pPr/w:shd]', namespaces=NS)]


@pytest.mark.asyncio
async def test_the_full_generic_export_takes_text_and_styles_from_the_compiled_presentation(tmp_path_factory):
    # V01: the actual route and worker; every authored paragraph once in order, each style from its presentation reference.
    workspace, content = await f10_export(tmp_path_factory)
    tree, header = xml(content), xml(content, 'word/header1.xml')
    body, position = emitted(tree), 0
    for value in body_texts(workspace.project.document):
        position = body.index(value, position) + len(value)
    assert styles(header, 'Alex Example') == [STYLES['name']] and styles(header, 'Backend engineer') == [STYLES['profession']]
    assert styles(tree, 'ФОКУС') == styles(tree, 'ПРОЕКТЫ') == styles(tree, 'О СЕБЕ') == [STYLES['section']]
    assert styles(tree, 'Example Labs') == styles(tree, 'Queue Platform') == [STYLES['project']]
    assert styles(tree, 'Implemented queue processing.') == styles(tree, F10_LINE) == [STYLES['body']]
    assert STYLES['emphasis'] in styles(tree, 'Python') and styles(tree, '3 years') == [STYLES['body']]
    # Bands come from the compiled heading kind: the projects and skill headings, not the plain ones.
    assert shaded(tree) == ['ПРОЕКТЫ', 'ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ', 'СУБД, ИНСТРУМЕНТЫ', 'ИНФРАСТРУКТУРА, ТАСК-МЕНЕДЖЕРЫ']


@pytest.mark.asyncio
async def test_renamed_headings_and_opaque_block_ids_keep_the_same_presentation(tmp_path_factory, tmp_path):
    # V01: nothing is inferred from block IDs or heading wording.
    workspace, content = await f10_export(tmp_path_factory)
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=workspace.project.template_package)
    document = request.document.model_copy(deep=True)
    for index, block in enumerate(walk([block for region in document.regions for block in region.blocks])):
        block.id = 'opaque-' + str(index)
        if text(block) == 'ПРОЕКТЫ':
            block.content[0].text = 'ОПЫТ РАБОТЫ'
    renamed = xml(render_captured_docx(recapture(request, document=document), tmp_path))
    original = xml(content)
    assert shaded(renamed) == ['ОПЫТ РАБОТЫ', *shaded(original)[1:]] and styles(renamed, 'ОПЫТ РАБОТЫ') == [STYLES['section']]
    assert [styles(renamed, value) for value in ['Example Labs', 'Implemented queue processing.', '3 years']] == [
        styles(original, value) for value in ['Example Labs', 'Implemented queue processing.', '3 years']]


@pytest.mark.asyncio
async def test_branded_export_carries_logo_repeating_footer_captured_fonts_and_exact_links(tmp_path_factory):
    # V04: assets are the captured bytes; the footer repeats on the first and every following page.
    workspace, content = await f10_export(tmp_path_factory)
    package, archive = workspace.project.template_package, parts(content)
    tree = xml(content)
    # The first-page header carries the logo and the body the Focus icon, both as the captured bytes.
    assets = {asset.id: asset.sha256 for asset in package.assets}
    def images(part):
        relations = etree.fromstring(archive['word/_rels/' + part + '.rels'])
        return [sha256(archive['word/' + child.get('Target')]) for child in relations if child.get('Type').endswith('/image')]
    assert images('header1.xml') == [assets['generic']] and images('document.xml') == [assets['python']]
    references = {(node.tag, node.get(qn('w:type'))) for node in tree.xpath('//w:sectPr/w:footerReference', namespaces=NS)}
    assert references == {(qn('w:footerReference'), 'default'), (qn('w:footerReference'), 'first')}
    assert tree.xpath('//w:sectPr/w:titlePg', namespaces=NS)
    footers = [name for name in archive if name.startswith('word/footer')]
    assert len(footers) == 2 and all(emitted(xml(content, name)) == 'mail@example.com' for name in footers)
    fonts, relations = xml(content, 'word/fontTable.xml'), etree.fromstring(archive['word/_rels/fontTable.xml.rels'])
    captured, embedded = {asset.sha256 for asset in package.assets if asset.role == 'font'}, set()
    for embed in fonts.xpath('//w:embedRegular|//w:embedBold|//w:embedItalic|//w:embedBoldItalic', namespaces=NS):
        key = uuid.UUID(embed.get(qn('w:fontKey')))
        target = next(child.get('Target') for child in relations if child.get('Id') == embed.get(qn('r:id')))
        raw = bytearray(archive['word/' + target])
        for index in range(32):
            raw[index] ^= key.bytes[::-1][index % 16]
        embedded.add(sha256(raw))
    assert embedded and embedded <= captured
    used = {run_font.get(qn('w:ascii')) for run_font in tree.iter(qn('w:rFonts'))}
    declared = {font.get(qn('w:name')) for font in fonts.xpath('//w:font[w:embedRegular or w:embedBold]', namespaces=NS)}
    assert used <= declared
    links = etree.fromstring(archive['word/_rels/document.xml.rels'])
    assert [child.get('Target') for child in links if child.get('TargetMode') == 'External'] == ['https://example.org/queue-tools']


@pytest.mark.asyncio
async def test_export_after_manual_text_and_format_edits_uses_the_authored_document(tmp_path_factory, tmp_path):
    # V03: edited wording, a manual bold mark and a corrected duration survive transfer into the actual export.
    from tests.templates.test_template_g02_views import edit, find, text_range, transferred
    _fixture, _result, workspace, originals = await shared(tmp_path_factory, 'F10-on')
    task = find(workspace, 'Implemented queue processing.', 'bullet_list')
    typed = edit(workspace, {'kind': 'replace_text', 'range': text_range(task, 0, len('Implemented')), 'text': 'Built',
        'styles': {}}, 'wording')
    summary = find(typed, 'Backend engineer focused on reliable queue systems.')
    start = text(summary).index('reliable')
    marked = edit(typed, {'kind': 'set_marks', 'range': text_range(summary, start, start + len('reliable')),
        'styles': {'bold': True}}, 'format')
    duration = find(marked, '3 years')
    corrected = edit(marked, {'kind': 'replace_text', 'range': text_range(duration, 0, 1), 'text': '4', 'styles': {}}, 'duration')
    content = await exported(tmp_path, transferred(corrected, originals), originals)
    tree = xml(content)
    body = emitted(tree)
    assert 'Built queue processing.' in body and 'Implemented queue processing.' not in body
    assert '4 years' in body and '3 years' not in body
    [bold] = styles(tree, 'reliable')
    assert bold != STYLES['body'] and (bold[2] == '1' or 'Light' not in bold[0])


def test_long_generic_content_flows_whole_and_in_order_through_the_actual_worker(tmp_path):
    # V02: F07 by direct admission (the durable import is blocked by S4-7) through the worker subprocess; nothing is capped.
    from tests.templates.test_captured_worker import run_worker
    workspace, _originals = direct_generic('F07', ['identity', 'projects', 'courses', 'portfolio'])
    lines = source_fixture('F07')[0].units[0].text.splitlines()
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=workspace.project.template_package)
    (tmp_path / 'template-docx-input.json').write_text(request.model_dump_json(by_alias=True))
    process = run_worker(tmp_path)
    assert process.returncode == 0, process.stderr.decode()
    content = (tmp_path / 'resume.docx').read_bytes()
    tree, body = xml(content), emitted(xml(content))
    for prefix, count in [('PROJECT-MARKER-', 250), ('SIDEBAR-MARKER-', 100)]:
        markers = [line for line in lines if line.startswith(prefix)]
        positions = [body.index(marker) for marker in markers]
        assert len(markers) == count and all(body.count(marker) == 1 for marker in markers) and positions == sorted(positions)
    assert emitted(xml(content, 'word/header1.xml')) == lines[0] + lines[1]
    links = etree.fromstring(parts(content)['word/_rels/document.xml.rels'])
    assert [child.get('Target') for child in links if child.get('TargetMode') == 'External'] == [lines[-1]]
    assert lines[-1] in body and views(workspace)['portfolio'] == ['ПОРТФОЛИО', lines[-1]]
    assert not tree.xpath('//w:cantSplit', namespaces=NS)


@pytest.mark.asyncio
async def test_long_generic_content_exports_through_the_service(tmp_path):
    # S4-7 under the default Settings limits (D096); the durable F07 import exports in test_generic_import.
    workspace, originals = direct_generic('F07', ['identity', 'projects', 'courses', 'portfolio'])
    body = emitted(xml(await exported(tmp_path, workspace, originals)))
    markers = [line for line in source_fixture('F07')[0].units[0].text.splitlines() if line.startswith('PROJECT-MARKER-')]
    assert [body.index(marker) for marker in markers] == sorted(body.index(marker) for marker in markers)


def test_a_column_does_not_start_with_keep_with_next_but_later_headings_keep_it(tmp_path):
    # Internal QA (S5): with the opening heading kept with its next line, the converter moved the whole two-column row
    # to page two and left page one empty; headings inside a column still stay with their first line.
    workspace, _originals = direct_generic('F07', ['identity', 'projects', 'courses', 'portfolio'])
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=workspace.project.template_package)
    tree = xml(render_captured_docx(request, tmp_path))
    def keep(paragraph):
        value = paragraph.xpath('string(w:pPr/w:keepNext/@w:val)', namespaces=NS)
        return paragraph.xpath('w:pPr/w:keepNext', namespaces=NS) != [] and value not in {'0', 'false', 'off'}
    first = [cell.xpath('w:p', namespaces=NS)[0] for cell in tree.xpath('//w:tbl/w:tr/w:tc', namespaces=NS)]
    assert [emitted(paragraph) for paragraph in first if emitted(paragraph)] == ['СЕРТИФИКАТЫ', 'ПРОЕКТЫ']
    assert not any(keep(paragraph) for paragraph in first)
    assert [emitted(paragraph) for paragraph in tree.xpath('//w:tbl//w:p', namespaces=NS) if keep(paragraph)] == ['ПОРТФОЛИО']
