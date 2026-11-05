"""Editable DOCX from exact authored content and captured template assets."""

from dataclasses import replace
import hashlib
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
import platform
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml.ns import qn
from docx.shared import Pt, Twips

from ..models.template_document import PresentedText, TemplateParagraphBlock
from ..models.template_render import TemplateRendererIdentity, TemplateRenderRequestV1
from ..rich_limits import DOCX_BYTES
from ..templates.compiler import ADDED_CAPABILITIES, CAPABILITIES
from ..hashing import canonical
from ..templates.focus import icon_catalog, row_icon
from ..templates.presentation_plan import chip_background, focus_row, hyperlink_target, table_rows
from ..templates.materialize_nodes import reference
from .captured_assets import CapturedAssets, decode_logo, decode_png
from .captured_embedding import embed_captured_fonts
from .captured_layout import BodyGeometry, CapturedMetrics, half_points, native_units
from .captured_styles import CapturedStyleResolver, authored_spans, resize_run, visible_text
from .docx_writer import Writer, element, fill
from .template import RenderFailure

ROOT = Path(__file__).resolve().parents[3]
RENDERER_VERSION = '1.0.0'
# Word draws no rounded run background: a chip is shaded text with a border of its own color as padding, and a
# whitespace separator between two chips is widened so the borders keep a visible gap.
CHIP_BORDER = 12
CHIP_GAP = 4
BLOCKS = {'section', 'paragraph', 'heading', 'bullet_list', 'numbered_list'}
NODES = {'text', 'join_fields', 'join_items', 'period', 'tags', 'bullets', 'link', 'focus_entry'}


def renderer_identity():
    sources = sorted((ROOT / 'packages/resume_core').rglob('*.py')) + [ROOT / 'requirements.txt']
    manifest = {'sources': {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources}, 'runtime': {'python': platform.python_version(), **{name: version(name)
        for name in ('fonttools', 'python-docx', 'lxml', 'pydantic', 'jsonschema', 'PyYAML', 'PyMuPDF', 'Pillow')}}}
    return TemplateRendererIdentity(id='captured-docx', version=RENDERER_VERSION,
        sha256=hashlib.sha256(canonical(manifest)).hexdigest())


def resolved_node(resolver, ref):
    resolver._reference(ref)
    node = resolver.views[ref.view_key].nodes[ref.node_index] if ref.node_index is not None else None
    if node is not None and node.type not in NODES:
        raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
    return node


def native_text(run, text):
    for part in re.split(r'(\r\n|\r|\n|\t)', text):
        if part in {'\r\n', '\r', '\n'}:
            run._r.append(element('w:br'))
        elif part == '\t':
            run._r.append(element('w:tab'))
        elif part:
            node = element('w:t')
            node.set(qn('xml:space'), 'preserve')
            node.text = part
            run._r.append(node)


def run_properties(style):
    font = style.selection.font
    props = element('w:rPr')
    props.append(element('w:rFonts', ascii=font.family, hAnsi=font.family, eastAsia=font.family, cs=font.family))
    italic = font.italic or style.slanted
    for tag, value in [('b', font.bold), ('bCs', font.bold), ('i', italic), ('iCs', italic), ('strike', style.strike)]:
        props.append(element('w:' + tag, val='1' if value else '0'))
    props.append(element('w:color', val=style.color.removeprefix('#')))
    if style.gap:
        props.append(element('w:spacing', val=native_units(style.gap)))
    size = half_points(style.size)
    props.append(element('w:sz', val=size))
    props.append(element('w:szCs', val=size))
    props.append(element('w:u', val='single' if style.underline else 'none'))
    if style.chip:
        props.append(element('w:bdr', val='single', sz=CHIP_BORDER, space=0, color=style.background.removeprefix('#')))
    if style.background is not None:
        fill(props, style.background)
    return props


def mark_properties(style):
    """Only the face and size of the paragraph mark: Word counts the mark in the last line of a paragraph."""
    kept = {qn('w:' + tag) for tag in ('rFonts', 'b', 'bCs', 'i', 'iCs', 'sz', 'szCs')}
    props = run_properties(style)
    props[:] = [child for child in props if child.tag in kept]
    return props


class CapturedWriter:
    compact = Writer.compact

    def floating_image(self, paragraph, path, width, height, x, y, *, label, horizontal='page', vertical='page', right=None):
        x, y, width, height = [native_units(value, 12700, positive=index > 1)
            for index, value in enumerate((x, y, width, height))]
        if x + width > (right or self.geometry.width) * 635 or y + height > self.geometry.height * 635:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        Writer.floating_image(self, paragraph, path, width / 12700, height / 12700, x / 12700, y / 12700,
            horizontal, vertical, label=label)
        anchor = paragraph._p.xpath('.//wp:anchor')[-1]
        anchor.find(qn('wp:positionH')).find(qn('wp:posOffset')).text = str(x)
        anchor.find(qn('wp:positionV')).find(qn('wp:posOffset')).text = str(y)
        for extent in [anchor.find(qn('wp:extent')), *anchor.iter(qn('a:ext'))]:
            extent.set('cx', str(width))
            extent.set('cy', str(height))

    def clear_cell(self, cell):
        Writer.clear_cell(self, cell)
        margins = cell._tc.get_or_add_tcPr().find(qn('w:tcMar'))
        margins[:] = [element('w:' + side, w=0, type='dxa')
            for side in ('top', 'start', 'left', 'bottom', 'end', 'right')]

    def __init__(self, request):
        self.request = request
        self.recipe = request.package.recipe
        self.geometry = BodyGeometry.from_recipe(self.recipe)
        if set(self.recipe.capabilities) - set(CAPABILITIES + ADDED_CAPABILITIES):
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        self.resolver = CapturedStyleResolver(request.package)
        self.metrics = CapturedMetrics()
        self.document = Document()
        self.numbering = self.document.part.numbering_part.element
        self.next_numbering = 6000
        self.next_drawing = 100000
        self.selections = {}
        self.slanted = set()
        self.widths = {}
        self.regions = {}
        def assign_width(blocks, width, region):
            for block in blocks:
                self.widths[block.id] = native_units(width, positive=True)
                self.regions[block.id] = region
                assign_width(block.children, width, region)
        layout = {region.id: region for region in self.recipe.layout.regions}
        for region in request.document.regions:
            # Without a sidebar column, blocks moved into the sidebar flow at the main width before the main ones.
            assign_width(region.blocks, layout.get(region.role, layout['main']).width, region.role)
        self.runs = {}
        self.links = {}
        self.paragraphs = {}
        self.logo = None
        # The block in work, so that a refusal can name it.
        self.block = None

    def prepare(self):
        request = self.request
        for block in request.document.blocks():
            self.block = block
            if block.type not in BLOCKS or block.type == 'section' and block.props.presentation == 'focus':
                raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
            resolved_node(self.resolver, block.presentation)
            if not isinstance(block.content, list):
                raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
            for span in block.content:
                if span.type not in {'text', 'fact_field', 'manual_scope', 'bound_link', 'link'}:
                    raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
                if span.type in {'bound_link', 'link'} and span.presentation is not None:
                    resolved_node(self.resolver, span.presentation)
            actual, links = [], []
            for span, link in authored_spans(block):
                resolved_node(self.resolver, span.presentation or block.presentation)
                text = visible_text(span.text)
                if not text:
                    continue
                style = self.resolver.run(block, span)
                chip = chip_background(block, span, self.recipe) if link is None else None
                if chip is not None:
                    style = replace(style, background=style.background or chip, chip=True)
                self.remember(style)
                actual.append((text, style))
                links.append(link)
            for index in range(1, len(actual) - 1):
                (_before, left), (text, style), (_after, right) = actual[index - 1:index + 2]
                if left.chip and right.chip and not style.chip and text.isspace() and not set(text) & set('\r\n\t'):
                    actual[index] = (text, replace(style, gap=CHIP_GAP / len(text)))
            self.runs[block.id] = actual
            self.links[block.id] = links
            emitted = (block.type != 'section' or block.content) and (self.regions[block.id] != 'header' or actual)
            self.paragraphs[block.id] = self.resolver.paragraph(block) if emitted else None
            if (self.paragraphs[block.id] is not None and self.regions[block.id] != 'header' and
                    native_units(self.paragraphs[block.id][0], positive=True) > self.geometry.bottom - self.geometry.continuation_top):
                raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
            if not actual and emitted:
                self.remember(self.generated(block, ''))
        self.block = None
        # Table rows (D143): each row's label in the table's label style, checked like any text before writing.
        self.table_rows = table_rows(request.document, self.recipe, request.package.definition.template.default_locale)
        self.row_labels = {}
        for block in request.document.blocks():
            row = self.table_rows.get(block.id)
            if row is None:
                continue
            self.block = block
            if self.regions[block.id] == 'header':
                raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
            table = self.recipe.style.tables[row['table']]
            ref = block.presentation.model_copy(update={'style_token': table.label_style}, deep=True)
            style = self.resolver.run(block, PresentedText(type='text', text=row['label'], styles={}, presentation=ref))
            self.remember(style)
            self.row_labels[block.id] = (visible_text(row['label']), style)
        self.block = None
        self.rows, self.icons, self.placed = {}, {}, []
        catalog = None
        for block in request.document.blocks():
            row = focus_row(block, self.recipe)
            if not row:
                continue
            if self.regions[block.id] == 'header':
                raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
            try:
                catalog = icon_catalog(request.package) if catalog is None else catalog
            except ValueError:
                raise RenderFailure('ASSET_MISMATCH') from None
            found = row_icon(request.package, request.facts, row, catalog, block.props.icon)
            icon = found[0] if found else None
            if found and icon not in self.icons:
                self.icons[icon] = decode_png(found[1], 'icon')
            self.rows[block.id] = (row, icon)
        self.configure_page()

    def remember(self, style):
        half_points(style.size)
        native_units(style.line_height, positive=True)
        self.selections[style.selection.font.sha256] = style.selection
        if style.slanted:
            self.slanted.add(style.selection.font.family)

    def generated(self, block, text):
        span = PresentedText(type='text', text=text, styles={}, presentation=None)
        return self.resolver.run(block, span)

    def configure_page(self):
        page, section = self.geometry, self.document.sections[0]
        section.page_width, section.page_height = Twips(page.width), Twips(page.height)
        section.top_margin, section.bottom_margin = Twips(page.continuation_top), Twips(page.height - page.bottom)
        section.left_margin, section.right_margin = Twips(page.left), Twips(page.right)
        section.header_distance = section.footer_distance = Twips(0)
        section.different_first_page_header_footer = True
        self.document.core_properties.author = ''
        self.document.core_properties.last_modified_by = ''
        normal = self.document.styles['Normal'].paragraph_format
        normal.space_before = normal.space_after = Twips(0)
        normal.keep_together = normal.keep_with_next = normal.widow_control = False

    def emit_run(self, paragraph, text, style):
        self.remember(style)
        run = paragraph.add_run()
        run._r.append(run_properties(style))
        native_text(run, text)
        return run

    def line_spacing(self, props, height, style, *, exact=False):
        """Google Docs reads w:line as a multiple of the single line whatever the rule says, so an exact 19 pt heading
        came out 28 pt there; a multiple of the font's single line gives Word and Docs one height."""
        single = self.metrics.single_line(style)
        spacing = props.find(qn('w:spacing'))
        if single is None or exact:
            spacing.set(qn('w:line'), str(native_units(height, positive=True)))
            spacing.set(qn('w:lineRule'), 'exact')
            return
        spacing.set(qn('w:line'), str(native_units(height / single, 240, positive=True)))
        spacing.set(qn('w:lineRule'), 'auto')

    def line_style(self, block):
        """The run that sets the paragraph's line, as CapturedStyleResolver.paragraph measures it."""
        styles = [style for _text, style in self.runs[block.id]]
        return max(styles, key=lambda style: style.line_height) if styles else self.generated(block, '')

    def band_padding(self, props, height, style, color):
        """Borders of the band's color pad its one text line to the band height, so the text stays centered as on
        screen: a line of the band's height left the heading at its top in Google Docs."""
        single = self.metrics.single_line(style)
        pad = (height - single) / 2 if single is not None else 0
        # A paragraph border is 1/4 to 12 pt wide and stands up to 31 whole points from the text.
        if not .25 <= pad <= 43:
            self.line_spacing(props, height, style)
            return
        space = min(31, round(pad - .25))
        borders = element('w:pBdr')
        for side in ('top', 'bottom'):
            borders.append(element('w:' + side, val='single', sz=max(2, round((pad - space) * 8)), space=space,
                color=color.removeprefix('#')))
        props.append(borders)
        self.line_spacing(props, single, style)

    def paragraph(self, container, block, *, header=False, depth=0, sequence=None, celled=False):
        self.block = block
        paragraph = container.add_paragraph()
        height, alignment = self.paragraphs[block.id]
        line = self.line_style(block)
        props = paragraph._p.get_or_add_pPr()
        props.append(element('w:spacing', before=0, after=0))
        # A multiple grows with chip borders in LibreOffice, so a chip line keeps its exact height.
        self.line_spacing(props, height, line, exact=any(style.chip for _text, style in self.runs[block.id]))
        props.append(element('w:jc', val='both' if alignment == 'justify' else alignment))
        props.append(element('w:widowControl', val=0))
        props.append(element('w:keepLines', val=0))
        is_heading = block.type == 'heading'
        props.append(element('w:keepNext', val=int(is_heading and self.recipe.layout.pagination.keep_heading_with_next)))
        view = self.resolver.views[block.presentation.view_key]
        band = is_heading and block.presentation.node_index is None and view.heading == 'band'
        node = resolved_node(self.resolver, block.presentation)
        focus = node is not None and node.type == 'focus_entry'
        inset = 0 if header or band or celled else view.inset + (self.recipe.style.focus.text_x if focus else 0)
        left = native_units(inset)
        if left >= self.widths[block.id]:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        props.append(element('w:ind', left=left, right=0))
        if band:
            band_style = self.recipe.style.section_band
            usable = self.widths[block.id] / 20 - band_style.text_inset
            if (usable <= 0 or height > band_style.height or
                    native_units(band_style.height, positive=True) > self.geometry.bottom - self.geometry.continuation_top or
                    any(any(control in text for control in '\r\n\t') for text, _style in self.runs[block.id]) or
                    self.metrics.paragraph_height(self.runs[block.id], usable, height) > height):
                raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
            props.find(qn('w:ind')).set(qn('w:firstLine'), str(native_units(band_style.text_inset)))
            color = self.recipe.style.colors[band_style.background]
            fill(props, color)
            self.band_padding(props, band_style.height, line, color)
        if is_heading:
            props.append(element('w:outlineLvl', val=block.props.level - 1))
        if block.type in {'bullet_list', 'numbered_list'}:
            if header:
                raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
            self.list_marker(paragraph, block, inset, depth, sequence)
        if not self.runs[block.id]:
            props.append(run_properties(self.generated(block, '')))
        else:
            props.append(mark_properties(line))
        previous_cr, current, hyperlink = False, None, None
        for (text, style), link in zip(self.runs[block.id], self.links[block.id], strict=True):
            run = self.emit_run(paragraph, text[1:] if previous_cr and text.startswith('\n') else text, style)
            previous_cr = text.endswith('\r')
            target = hyperlink_target(link.href) if link is not None else None
            if target is None:
                current = None
                continue
            # Consecutive runs of one link share its element; equal targets share one relationship.
            if link is not current:
                current, hyperlink = link, element('w:hyperlink')
                hyperlink.set(qn('r:id'), paragraph.part.relate_to(target, RELATIONSHIP_TYPE.HYPERLINK, is_external=True))
                paragraph._p.append(hyperlink)
            hyperlink.append(run._r)
        self.block = None
        return paragraph

    def list_marker(self, paragraph, block, inset, depth, sequence):
        if depth > 8:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        bullets = self.recipe.style.bullets
        if bullets.marker_offset > bullets.text_offset:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        numbered = block.type == 'numbered_list'
        start = block.props.start if numbered else None
        index = (start or (sequence.get('index', 0) + 1 if sequence.get('kind') == 'numbered_list' else 1)) if numbered else 1
        if not 1 <= index <= 2147483647:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        marker = f'{index}.' if numbered else bullets.marker
        # A marker above the text's size sets a taller first line in Google Docs, which keeps no exact line; the
        # screen draws it at the text's size.
        text = self.generated(block, marker)
        style = resize_run(text, min(bullets.marker_size, text.size))
        self.remember(style)
        left = native_units(inset + bullets.text_offset * (depth + 1))
        marker_left = native_units(inset + bullets.text_offset * depth + bullets.marker_offset)
        if left >= self.widths[block.id]:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        signature = (numbered, style.selection.font.family, style.selection.font.sha256,
            style.size, style.color, left, marker_left)
        identifier = sequence.get('num') if start is None and sequence.get('signature') == signature else None
        if identifier is None:
            identifier = self.next_numbering
            self.next_numbering += 1
            abstract = element('w:abstractNum', abstractNumId=identifier)
            abstract.append(element('w:multiLevelType', val='singleLevel'))
            level = element('w:lvl', ilvl=0)
            level.append(element('w:start', val=index))
            level.append(element('w:numFmt', val='decimal' if numbered else 'bullet'))
            level.append(element('w:lvlText', val='%1.' if numbered else marker))
            level.append(element('w:lvlJc', val='left'))
            props = element('w:pPr')
            tabs = element('w:tabs')
            tabs.append(element('w:tab', val='num', pos=left))
            props.append(tabs)
            props.append(element('w:ind', left=left, hanging=left - marker_left))
            level.append(props)
            level.append(run_properties(style))
            abstract.append(level)
            first_num = self.numbering.find(qn('w:num'))
            if first_num is None:
                self.numbering.append(abstract)
            else:
                first_num.addprevious(abstract)
            number = element('w:num', numId=identifier)
            number.append(element('w:abstractNumId', val=identifier))
            self.numbering.append(number)
        sequence.update(num=identifier, index=index, signature=signature, kind=block.type)
        props = paragraph._p.get_or_add_pPr()
        existing = props.find(qn('w:ind'))
        existing.set(qn('w:left'), str(left))
        existing.set(qn('w:hanging'), str(left - marker_left))
        number = element('w:numPr')
        number.append(element('w:ilvl', val=0))
        number.append(element('w:numId', val=identifier))
        props.insert(0, number)

    def blocks(self, container, blocks, depth=0, *, in_row=False):
        sequence = {}
        unfilled = unfilled_lines(blocks, self.resolver, self.runs)
        table = None
        index, tabled = 0, False
        while index < len(blocks):
            block = blocks[index]
            index += 1
            if block.id in unfilled:
                continue
            if block.id in self.table_rows:
                # Rows of one table style that follow each other are one table; two tables stay apart by a paragraph.
                run, style = [block], self.table_rows[block.id]['table']
                while index < len(blocks) and self.table_rows.get(blocks[index].id, {}).get('table') == style:
                    run.append(blocks[index])
                    index += 1
                if tabled:
                    self.spacer(container, 1)
                self.key_value_table(container, run, depth)
                table, tabled = None, True
                sequence.clear()
                continue
            tabled = False
            if block.type not in {'bullet_list', 'numbered_list'}:
                sequence.clear()
            if block.type != 'section' or block.content:
                self.paragraph(container, block, depth=depth, sequence=sequence)
            row, icon = self.rows.get(block.id, ([], None))
            if row:
                table = table or self.focus_table(container, block)
                self.blocks(self.focus_row(table, block, row, icon, depth), block.children[len(row):], depth)
                continue
            table = None
            self.blocks(container, block.children, depth + (block.type in {'bullet_list', 'numbered_list'}), in_row=in_row)
            # An item inside a table cell keeps no gap of its own; the table ends with it.
            if block.type == 'section' and block.children and not in_row:
                gap = self.resolver.views[block.presentation.view_key].item_gap
                if gap:
                    self.spacer(container, native_units(gap, positive=True))

    def key_value_table(self, container, rows, depth):
        """A run of table rows as one table: the label cell in the table's label style, the content cell with the row's
        own blocks, borders and cell margins from the table style (D143)."""
        first = rows[0]
        style = self.recipe.style.tables[self.table_rows[first.id]['table']]
        inset = native_units(self.resolver.views[first.presentation.view_key].inset)
        width = self.widths[first.id] - inset
        label = native_units(style.label_width)
        widths = [label, width - label] if label else [width]
        padding = native_units(style.padding_x)
        if widths[-1] <= 2 * padding:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        table = container.add_table(0, len(widths))
        if not isinstance(container, type(self.document)):
            container.paragraphs[-1]._p.getparent().remove(container.paragraphs[-1]._p)
        self.borderless(table, widths)
        props = table._tbl.tblPr
        if inset:
            props.find(qn('w:tblInd')).set(qn('w:w'), str(inset))
        if style.border_width > 0:
            color = self.recipe.style.colors[style.border_color].removeprefix('#')
            size = native_units(style.border_width, 8, positive=True, maximum=96)
            for side in props.find(qn('w:tblBorders')):
                side.set(qn('w:val'), 'single')
                side.set(qn('w:sz'), str(size))
                side.set(qn('w:space'), '0')
                side.set(qn('w:color'), color)
        margins = element('w:tblCellMar')
        for side, value in (('top', style.padding_y), ('left', style.padding_x), ('bottom', style.padding_y), ('right', style.padding_x)):
            margins.append(element('w:' + side, w=native_units(value), type='dxa'))
        props.append(margins)
        for block in rows:
            self.block = block
            cells = table.add_row().cells
            for cell, cell_width in zip(cells, widths, strict=True):
                cell.width = Twips(cell_width)
            if label:
                self.label_cell(cells[0], block, style)
            content = cells[-1]
            if style.background is not None:
                fill(content._tc.get_or_add_tcPr(), self.recipe.style.colors[style.background])
            # A new cell holds one empty paragraph; the row's blocks take its place, and a cell still ends in a paragraph.
            for paragraph in content.paragraphs:
                paragraph._p.getparent().remove(paragraph._p)
            self.assign_width(block.children, widths[-1] - 2 * padding)
            self.blocks(content, block.children, depth, in_row=True)
            if content._tc[-1].tag != qn('w:p'):
                self.spacer(content, 1)
        self.block = None
        gap = self.table_rows[rows[-1].id].get('gap')
        if gap:
            self.spacer(container, native_units(gap, positive=True))

    def assign_width(self, blocks, width):
        for block in blocks:
            self.widths[block.id] = width
            self.assign_width(block.children, width)

    def label_cell(self, cell, block, table):
        text, style = self.row_labels[block.id]
        props = cell._tc.get_or_add_tcPr()
        if table.label_background is not None:
            fill(props, self.recipe.style.colors[table.label_background])
        if table.label_align == 'center':
            props.append(element('w:vAlign', val='center'))
        paragraph = cell.paragraphs[0]
        pprops = paragraph._p.get_or_add_pPr()
        pprops.append(element('w:spacing', before=0, after=0))
        self.line_spacing(pprops, style.line_height, style)
        pprops.append(element('w:jc', val='left'))
        pprops.append(element('w:widowControl', val=0))
        pprops.append(element('w:ind', left=0, right=0))
        pprops.append(mark_properties(style))
        if text:
            self.emit_run(paragraph, text, style)

    def focus_table(self, container, section):
        """Focus rows as one borderless table: Google Docs moves floating pictures, a cell keeps an icon beside its text."""
        first = native_units(self.resolver.views[section.presentation.view_key].inset + self.recipe.style.focus.text_x, positive=True)
        widths = (first, self.widths[section.id] - first)
        if widths[1] <= 0:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        table = container.add_table(0, 2)
        # A table needs no closing paragraph unless it ends its cell, and columns() sees to that.
        if not isinstance(container, type(self.document)):
            container.paragraphs[-1]._p.getparent().remove(container.paragraphs[-1]._p)
        self.borderless(table, widths)
        return table

    def focus_row(self, table, section, row, icon, depth):
        """Focus text centered in at least the minimum row height; the decorative icon centered in its box."""
        style = self.recipe.style.focus
        view = self.resolver.views[row[0].presentation.view_key]
        widths = [column.width.twips for column in table.columns]
        cells = table.add_row().cells
        properties = cells[0]._tc.getparent().get_or_add_trPr()
        properties.append(element('w:cantSplit'))
        # The gap between rows is part of the row: Word and LibreOffice count a cell's bottom margin differently.
        height = native_units(style.minimum_row_height, positive=True) + native_units(view.item_gap)
        properties.append(element('w:trHeight', val=height, hRule='atLeast'))
        for cell, width in zip(cells, widths, strict=True):
            cell.width = Twips(width)
            self.clear_cell(cell)
            cell._tc.tcPr.append(element('w:vAlign', val='center'))
        if icon is None:
            self.spacer(cells[0], 1)
        else:
            image = self.icons[icon]
            scale = min(style.icon_width / image.width, style.icon_height / image.height)
            width, height = image.width * scale, image.height * scale
            holder = cells[0].add_paragraph()
            holder.paragraph_format.space_before = holder.paragraph_format.space_after = Twips(0)
            holder.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self.placed.append((holder, icon, width, height))
        for block in row:
            self.paragraph(cells[1], block, depth=depth, sequence={}, celled=True)
        return cells[1]

    def spacer(self, container, height):
        paragraph = container.add_paragraph()
        self.compact(paragraph, height / 20)
        paragraph.paragraph_format.line_spacing = Twips(height)
        paragraph.paragraph_format.widow_control = False
        if self.selections:
            # Google Docs takes the exact height as a multiple of the mark's single line: a mark whose single line is
            # 12 pt keeps the gap there too.
            selection = next(iter(self.selections.values()))
            size = max(2, round(24 / self.metrics.metrics(selection)[2]))
            family = selection.font.family
            props = element('w:rPr')
            props.append(element('w:rFonts', ascii=family, hAnsi=family, eastAsia=family, cs=family))
            props.append(element('w:sz', val=size))
            props.append(element('w:szCs', val=size))
            paragraph._p.get_or_add_pPr().append(props)
        return paragraph

    def header_line(self, paragraph, x, width, before):
        """A header line by spacing and indents, not a Word frame: Google Docs drops frames and stacks their text."""
        left, native_width = native_units(x), native_units(width, positive=True)
        if left + native_width > self.geometry.width:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        props = paragraph._p.get_or_add_pPr()
        indent = props.find(qn('w:ind'))
        indent.set(qn('w:left'), str(left - self.geometry.left))
        indent.set(qn('w:right'), str(self.geometry.width - self.geometry.right - left - native_width))
        props.find(qn('w:spacing')).set(qn('w:before'), str(native_units(before)))

    def header(self):
        header = self.document.sections[0].first_page_header
        anchor = .05
        self.compact(header.paragraphs[0], anchor)
        recipe = self.recipe.style.header
        region = self.recipe.layout.regions[0]
        # Source fallback lines stack from the first slot; growth counts from the last slot, as if they filled both.
        first, last = min(recipe.name_top, recipe.profession_top), max(recipe.name_top, recipe.profession_top)
        cursor = anchor
        growth = 0.0
        for block in self.request.document.regions[0].blocks:
            for child in self.header_blocks(block):
                if not self.runs[child.id]:
                    continue
                refs = [span.presentation or child.presentation for span, _link in authored_spans(child) if visible_text(span.text)]
                if self.header_fallback(child, refs):
                    top, designed = first, last
                else:
                    slots = {getattr(resolved_node(self.resolver, ref), 'header_slot', None) for ref in refs}
                    if len(slots) != 1 or None in slots:
                        raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
                    top = designed = getattr(recipe, next(iter(slots)) + '_top')
                height = self.metrics.paragraph_height(self.runs[child.id], region.width, self.paragraphs[child.id][0])
                paragraph = self.paragraph(header, child, header=True)
                y = max(top, cursor)
                self.header_line(paragraph, region.x, region.width, y - cursor)
                cursor = y + height
                growth = max(growth, cursor - designed - self.paragraphs[child.id][0])
        if cursor > self.recipe.style.page.body_bottom or self.recipe.style.page.first_body_top + growth >= self.recipe.style.page.body_bottom:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        return growth, cursor

    def header_fallback(self, block, refs):
        """A paragraph of source wording a header block kept: no view node, the block's own fallback style."""
        if block.type != 'paragraph' or not refs or any(resolved_node(self.resolver, ref) is not None for ref in refs):
            return False
        keys = {ref.view_key for ref in refs}
        if len(keys) != 1:
            return False
        view = self.resolver.views[next(iter(keys))]
        style = view.fallback_style or (view.nodes[0].style if view.nodes else None)
        return all(ref.style_token == style for ref in refs)

    def header_blocks(self, block):
        if block.type != 'section' or block.content:
            yield block
        for child in block.children:
            yield from self.header_blocks(child)

    def footer(self):
        recipe = self.recipe.style.footer
        if not recipe.text:
            return
        ref = reference(self.request.package, next(iter(self.recipe.views)), recipe.style, 'captured-footer')
        block = TemplateParagraphBlock(type='paragraph', id='captured-footer', revision=1, props={},
            content=[PresentedText(type='text', text=recipe.text, styles={}, presentation=None)],
            children=[], provenance=[], presentation=ref)
        style = self.generated(block, recipe.text)
        width = min(recipe.center_x, self.recipe.style.page.width - recipe.center_x) * 2
        top = recipe.baseline_y - self.metrics.ascent(style)
        distance = self.recipe.style.page.height - recipe.baseline_y - (style.line_height - self.metrics.ascent(style))
        if top < 0 or width <= 0 or recipe.baseline_y > self.recipe.style.page.height or distance < 0:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        self.document.sections[0].footer_distance = Twips(native_units(distance))
        left = -self.geometry.left + native_units(recipe.center_x - width / 2)
        right = self.geometry.width - self.geometry.right - native_units(recipe.center_x + width / 2)
        for footer in (self.document.sections[0].footer, self.document.sections[0].first_page_footer):
            paragraph = footer.paragraphs[0]
            self.compact(paragraph, style.line_height)
            props = paragraph._p.get_or_add_pPr()
            self.line_spacing(props, style.line_height, style)
            props.append(element('w:jc', val='center'))
            props.append(element('w:ind', left=left, right=right))
            props.append(mark_properties(style))
            self.emit_run(paragraph, recipe.text, style)

    def first_page_spacer(self, growth, header_bottom):
        # A header taller than the top margin starts the body below itself.
        start = max(self.geometry.continuation_top, native_units(header_bottom))
        total = max(0, self.geometry.first_top + native_units(growth) - start)
        divider = self.recipe.style.header.divider
        if divider is None:
            if total:
                self.spacer(self.document, total)
            return
        page = self.recipe.style.page
        if not page.continuation_body_top <= divider.y <= page.first_body_top:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        x1, x2 = native_units(divider.x1), native_units(divider.x2)
        thickness = native_units(divider.width, 8, positive=True, maximum=96)
        target = native_units(divider.y + growth) - start
        before = max(0, target - 1)
        after = total - before - 1
        if x1 >= x2 or x2 > self.geometry.width or thickness < 2 or after < 0:
            raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
        if before:
            self.spacer(self.document, before)
        paragraph = self.spacer(self.document, 1)
        props = paragraph._p.get_or_add_pPr()
        props.append(element('w:ind', left=x1 - self.geometry.left,
            right=self.geometry.width - self.geometry.right - x2))
        borders = element('w:pBdr')
        borders.append(element('w:bottom', val='single', color=self.recipe.style.colors[divider.color][1:],
            sz=thickness, space=0))
        props.append(borders)
        if after:
            self.spacer(self.document, after)

    def borderless(self, table, widths):
        table.autofit = False
        props = table._tbl.tblPr
        props.find(qn('w:tblW')).set(qn('w:w'), str(sum(widths)))
        props.find(qn('w:tblW')).set(qn('w:type'), 'dxa')
        props.append(element('w:tblInd', w=0, type='dxa'))
        borders = element('w:tblBorders')
        for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
            borders.append(element('w:' + side, val='nil'))
        props.append(borders)
        for index, width in enumerate(widths):
            table.columns[index].width = Twips(width)

    def columns(self):
        """The sidebar and main columns as one borderless table row, in page order: the sidebar left or right of main."""
        geometry, roles = self.geometry, {region.role: region for region in self.request.document.regions}
        cells = [(geometry.sidebar_width, roles.get('sidebar')), (geometry.main_width, roles.get('main'))]
        if geometry.sidebar_right:
            cells.reverse()
        if geometry.gap:
            cells.insert(1, (geometry.gap, None))
        widths = [width for width, _region in cells]
        table = self.document.add_table(rows=1, cols=len(widths))
        self.borderless(table, widths)
        for index, (width, region) in enumerate(cells):
            cell = table.cell(0, index)
            cell.width = Twips(width)
            self.clear_cell(cell)
            if region is not None:
                self.blocks(cell, region.blocks)
                # A column's first paragraph opens the body; keeping it with the next one adds nothing there,
                # but converters then move the whole column row to the next page and leave page one empty.
                keep = cell.paragraphs[0]._p.pPr.find(qn('w:keepNext')) if cell.paragraphs and cell.paragraphs[0]._p.pPr is not None else None
                if keep is not None:
                    keep.set(qn('w:val'), '0')
            # A cell ends in a paragraph, also after a Focus table.
            if cell._tc[-1].tag != qn('w:p'):
                self.spacer(cell, 1)

    def render(self, workspace):
        growth, header_bottom = self.header()
        self.footer()
        self.first_page_spacer(growth, header_bottom)
        if self.geometry.sidebar_width:
            self.columns()
        else:
            # One column: the body itself is the main column, in reading order, with no layout table.
            for region in self.request.document.regions[1:]:
                self.blocks(self.document, region.blocks)
            body = self.document.element.body
            if len(body) > 1 and body[-2].tag == qn('w:tbl'):
                self.spacer(self.document, 1)
        # A logo place without an asset stays empty (D145).
        logo = self.recipe.style.header.logo if self.recipe.style.header.logo and self.recipe.style.header.logo.asset else None
        if logo is not None:
            asset = next(asset for asset in self.request.package.assets if asset.id == logo.asset)
            self.logo = decode_logo(asset)
        paths = CapturedAssets({selection.font.asset_id: selection.font for selection in self.selections.values()}, self.logo,
            self.icons).materialize(workspace)
        for paragraph, icon, width, height in self.placed:
            inline = paragraph.add_run().add_picture(str(paths[icon]), width=Pt(width), height=Pt(height))._inline
            inline.docPr.set('descr', '')
            # Without them LibreOffice leaves a margin beside the picture.
            for side in ('distT', 'distB', 'distL', 'distR'):
                inline.set(side, '0')
        if logo is not None:
            ratio = min(logo.width / self.logo.width, logo.height / self.logo.height)
            width, height = self.logo.width * ratio, self.logo.height * ratio
            x, top = logo.x + (logo.width - width) / 2, logo.top + (logo.height - height) / 2
            if x + width > self.recipe.style.page.width or top + height > self.recipe.style.page.height:
                raise RenderFailure('RICH_EXPORT_UNSUPPORTED')
            self.floating_image(self.document.sections[0].first_page_header.paragraphs[0], paths[logo.asset], width, height, x, top,
                label='Captured template logo')
        raw = BytesIO()
        self.order_properties()
        self.document.save(raw)
        if len(raw.getvalue()) > DOCX_BYTES:
            raise RenderFailure('RENDER_OUTPUT_LIMIT')
        # Word slants an upright face only while its family embeds no italic, so one such run decides for the family.
        return embed_captured_fonts(raw.getvalue(), [selection for selection in self.selections.values()
            if not (selection.font.italic and selection.font.family in self.slanted)])

    def order_properties(self):
        names = ('pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl',
            'numPr', 'pBdr', 'shd', 'tabs', 'spacing', 'ind', 'jc', 'outlineLvl', 'rPr')
        order = {qn('w:' + name): index for index, name in enumerate(names)}
        for part in self.document.part.package.parts:
            root = getattr(part, 'element', None)
            if root is None:
                continue
            for props in root.iter(qn('w:pPr')):
                props[:] = sorted(props, key=lambda child: order.get(child.tag, len(order)))
            table_names = ('tblStyle', 'tblpPr', 'tblOverlap', 'bidiVisual', 'tblStyleRowBandSize',
                'tblStyleColBandSize', 'tblW', 'jc', 'tblCellSpacing', 'tblInd', 'tblBorders', 'shd',
                'tblLayout', 'tblCellMar', 'tblLook', 'tblCaption', 'tblDescription', 'tblPrChange')
            table_order = {qn('w:' + name): index for index, name in enumerate(table_names)}
            for props in root.iter(qn('w:tblPr')):
                props[:] = sorted(props, key=lambda child: table_order.get(child.tag, len(table_order)))
            cell_names = ('cnfStyle', 'tcW', 'gridSpan', 'hMerge', 'vMerge', 'tcBorders', 'shd', 'noWrap', 'tcMar',
                'textDirection', 'tcFitText', 'vAlign', 'hideMark')
            cell_order = {qn('w:' + name): index for index, name in enumerate(cell_names)}
            for props in root.iter(qn('w:tcPr')):
                props[:] = sorted(props, key=lambda child: cell_order.get(child.tag, len(cell_order)))


def unfilled_lines(blocks, resolver, runs):
    """Lines of a new job nobody typed in, with the labels they would follow: a blank line never reaches the DOCX."""
    def blank(block):
        node = resolved_node(resolver, block.presentation)
        return (block.type in {'paragraph', 'bullet_list'} and not block.children and not runs[block.id] and not block.content
            and node is not None and node.type in {'text', 'bullets'})
    found = {block.id for block in blocks if blank(block)}
    for index, block in enumerate(blocks[:-1]):
        node = resolved_node(resolver, block.presentation)
        if blocks[index + 1].id in found and node is not None and node.type == 'bullets' and block.type == 'paragraph':
            found.add(block.id)
    return found


def located(block):
    """What an export refusal says about its place: the block, and the text the user can find it by."""
    if block is None:
        return {}
    spans = authored_spans(block) if isinstance(block.content, list) else ()
    return {'blockId': block.id, 'fragment': ' '.join(''.join(getattr(span, 'text', None) or '' for span, _link in spans).split())[:60]}


def render_captured_docx(request, workspace):
    request = TemplateRenderRequestV1.model_validate(request.model_dump(mode='json', by_alias=True))
    if request.renderer != renderer_identity():
        raise RenderFailure('RENDERER_MISMATCH')
    writer = CapturedWriter(request)
    try:
        writer.prepare()
        return writer.render(workspace)
    except RenderFailure as error:
        raise RenderFailure(error.code, located(writer.block)) from None
