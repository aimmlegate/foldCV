"""S5: the Generic 2.1.0 package through the actual export route and captured worker (V01, V03, V04) and long content (V02)."""

import uuid

import pytest
from docx.oxml.ns import qn
from lxml import etree

from packages.resume_core.models.template_render import TemplateRenderRequestV1
from packages.resume_core.rendering.captured_docx import render_captured_docx, renderer_identity
from packages.resume_core.template_export import capture_export, snapshot_identity
from packages.resume_core.templates.compiler import sha256
from packages.resume_core.templates.focus import icon_catalog
from tests.templates.generic_fixtures import direct_generic, generic_import, export_through_service as exported
from tests.templates.storage_fixtures import source_fixture
from tests.templates.test_captured_docx import NS, emitted, parts, recapture, xml
from tests.templates.test_generic_import import body, shared, views
from tests.templates.test_template_view_adapters import text


pytestmark = pytest.mark.slow

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
    python = icon_catalog(package).files['python'].sha256
    assert images('header1.xml') == [assets['generic']] and images('document.xml') == [python]
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


def refused_identity(refuse, repair=None):
    """Identity answers the coordinator refuses on every attempt; other blocks answer as scripted. repair, when
    given, answers the repair slot instead of refuse."""
    def wrap(script):
        def scripted(request, value):
            if 'targets' in value or value['declaration']['id'] != 'identity':
                return script(request, value)
            # A repair has no earlier items to select, so it starts from the first reply's shape.
            reply = script(request, {**value, 'slot': 'initial'})
            return (repair or refuse)(reply) if value.get('slot', 'initial') != 'initial' else refuse(reply)
        return scripted
    return wrap


def unstated_profession(reply):
    # A title no source line states, sent without its entry: the first reply is refused with the binding named.
    # A reworded title is not refused any more, because its word stems bind it to the line it rewords (I2).
    reply['payload'] = {**reply['payload'], 'profession': 'Chief quantum officer'}
    reply['fields'] = [field for field in reply['fields'] if field['fieldKey'] != 'profession']
    return reply


def unreadable(_reply):
    # A repair that does not parse cannot drop the unstated title (I4), so no attempt is admitted.
    return 'not a JSON reply'


def frames(tree):
    """(top in twips, text) of every framed paragraph with text."""
    return [(int(paragraph.xpath('string(w:pPr/w:framePr/@w:y)', namespaces=NS)), emitted(paragraph))
        for paragraph in tree.xpath('//w:p[w:pPr/w:framePr]', namespaces=NS) if emitted(paragraph)]


@pytest.mark.asyncio
async def test_a_refused_identity_reply_keeps_its_cited_lines_in_the_header_and_every_other_block(tmp_path):
    # P05: the failed block shows only the lines it cited, in its own view and fallback style; accepted blocks
    # of other views stay (R05, K02), and the header exports the fallback text instead of refusing it.
    _fixture, result, workspace, originals = await generic_import(tmp_path / 'import', 'F01',
        wrap=refused_identity(unstated_profession, repair=unreadable))
    identity = next(task for task in result.tasks if task.block_id == 'identity')
    assert result.state == 'published' and identity.state == 'source_fallback'
    shown = views(workspace)
    # The two cited lines are adjacent in the source, so they stay one paragraph with its line break.
    assert shown['identity'] == ['Alex Example\nBackend engineer']
    assert shown['summary'][1] == 'Backend engineer who implemented queue processing.'
    assert 'Implemented queue processing.' in shown['projects'] and shown['programming'][1] == 'Python'
    [issue] = [issue for issue in workspace.project.import_issues if issue.code == 'IMPORT_SOURCE_FALLBACK']
    assert issue.message == 'Показан исходный текст: проверку извлечённых данных не удалось завершить.'
    # The notice points at the identity view's own fallback paragraph, not at every block of the page.
    shown_blocks = [block for block in workspace.project.document.blocks()
        if block.type != 'section' and block.presentation.view_key == 'identity']
    assert issue.block_ids == [block.id for block in shown_blocks]
    content = await exported(tmp_path / 'export', workspace, originals)
    header = xml(content, 'word/header1.xml')
    [(top, value)] = frames(header)
    assert value == 'Alex Example\nBackend engineer' and styles(header, 'Alex ExampleBackend engineer') == [STYLES['body']]
    # It starts at the name slot and ends above the first body line.
    recipe = workspace.project.template_package.recipe.style
    assert top == round(recipe.header.name_top * 20)
    assert top + 2 * recipe.text['body'].line_height * 20 <= recipe.page.first_body_top * 20
    assert 'Implemented queue processing.' in emitted(xml(content))


@pytest.mark.asyncio
async def test_an_identity_block_without_a_usable_reply_places_no_lines_of_its_whole_cv_scope(tmp_path):
    # No reply is not evidence of absence, so the block is a source fallback with a notice. Its scope is the whole
    # CV, which identifies no lines: LIVE-08 placed every unshown line, contacts included, so none are placed now.
    _fixture, result, workspace, originals = await generic_import(tmp_path / 'import', 'F01',
        wrap=refused_identity(lambda _reply: 'not a JSON reply'))
    assert next(task for task in result.tasks if task.block_id == 'identity').state == 'source_fallback'
    shown = views(workspace)
    assert 'identity' not in shown and shown['summary'][1] == 'Backend engineer who implemented queue processing.'
    assert 'Implemented queue processing.' in shown['projects']
    assert body(workspace).count('Our team reduced median latency from 800 ms to 500 ms.') == 1
    [issue] = [issue for issue in workspace.project.import_issues if issue.code == 'IMPORT_SOURCE_FALLBACK']
    assert issue.message.startswith('Блок не заполнен') and issue.block_ids
    content = await exported(tmp_path / 'export', workspace, originals)
    assert frames(xml(content, 'word/header1.xml')) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('style', ['body', 'name'])
async def test_unslotted_header_text_renders_only_in_its_block_fallback_style(tmp_path_factory, tmp_path, style):
    # A header block's own fallback paragraph stacks from the name slot; other text without a slot still refuses.
    from packages.resume_core.rendering.template import RenderFailure
    workspace, _content = await f10_export(tmp_path_factory)
    _attempt, capture = capture_export(workspace, snapshot_identity(workspace), renderer_identity())
    request = TemplateRenderRequestV1(**capture.request.model_dump(by_alias=True), package=workspace.project.template_package)
    document = request.document.model_copy(deep=True)
    [name] = [block for block in walk(document.regions[0].blocks) if text(block) == 'Alex Example']
    for part in name.content:
        part.presentation = part.presentation.model_copy(update={'node_index': None, 'style_token': style})
    if style == 'name':
        with pytest.raises(RenderFailure, match='RICH_EXPORT_UNSUPPORTED'):
            render_captured_docx(recapture(request, document=document), tmp_path)
        return
    header = xml(render_captured_docx(recapture(request, document=document), tmp_path), 'word/header1.xml')
    recipe = workspace.project.template_package.recipe.style
    assert styles(header, 'Alex Example') == [STYLES['body']] and styles(header, 'Backend engineer') == [STYLES['profession']]
    assert frames(header)[0] == (round(recipe.header.name_top * 20), 'Alex Example')
