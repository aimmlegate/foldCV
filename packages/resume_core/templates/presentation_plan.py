"""One presentation plan for the mounted editor and the DOCX writer: decisions Python makes from the captured package."""

from urllib.parse import urlsplit

from ..rendering.captured_styles import authored_spans
from ..hashing import canonical, sha256
from .focus import catalog_for, row_icon
from .materialize_nodes import locale_text
from .models import remember_asset
from .materialize_nodes import focus_row, node_of


def hyperlink_target(href):
    """The exact target when it is an absolute web or mail address; any other link text stays plain text."""
    if not href or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in href):
        return None
    try:
        parts = urlsplit(href)
        host = parts.hostname if parts.scheme in {'http', 'https'} else None
    except ValueError:
        return None
    return href if host or parts.scheme == 'mailto' and parts.path else None




def is_band(block, recipe):
    """A view title heading in a view whose compiled heading is a band; never inferred from wording or IDs."""
    ref = block.presentation
    return (block.type == 'heading' and ref is not None and ref.node_index is None
        and recipe.views[ref.view_key].heading == 'band')


def chip_background(block, span, recipe):
    """The chip color of a fact or edit-scope span that a tags node with a background shows; None for other spans.
    Separators stay plain text, so each technology reads as its own chip."""
    if span.type not in {'fact_field', 'manual_scope'} or not span.text:
        return None
    node = node_of(recipe, span.presentation or block.presentation)
    return recipe.style.colors[node.background] if node is not None and node.type == 'tags' and node.background else None


def table_of(recipe, block):
    """(table style id, label per locale) of a table row section (D143); None for any other block. Both come from the
    captured view: the block's own row label, or the label of the node that opened the row."""
    ref = getattr(block, 'presentation', None)
    if block.type != 'section' or block.props.presentation != 'row' or ref is None or ref.view_key not in recipe.views:
        return None
    view = recipe.views[ref.view_key]
    if view.table is None or view.table not in recipe.style.tables:
        return None
    label = view.row if ref.node_index is None else view.nodes[ref.node_index].row
    return view.table, label or {}


def table_rows(document, recipe, locale):
    """Each row section's table, label and place: rows of one table style that follow each other among siblings share
    one table, so the first and the last of them carry its outer edges. A table of whole blocks ends with the last
    block's item gap; a table inside an entry leaves the gap to the entry."""
    found = {}
    def visit(items):
        previous = None
        for index, block in enumerate(items):
            table = table_of(recipe, block)
            if table is not None:
                following = table_of(recipe, items[index + 1]) if index + 1 < len(items) else None
                last = following is None or following[0] != table[0]
                ref = block.presentation
                gap = recipe.views[ref.view_key].item_gap if last and ref.node_index is None else 0
                found[block.id] = {'table': table[0], 'label': locale_text(table[1], locale),
                    'first': previous is None or previous[0] != table[0], 'last': last, **({'gap': gap} if gap else {})}
            previous = table
            visit(block.children)
    for region in document.regions:
        visit(region.blocks)
    return found




_RESOLVERS = {}


def resolver(package):
    from ..rendering.captured_fonts import CapturedFontResolver
    found = _RESOLVERS.get(package.package_hash)
    if found is None:
        found = _RESOLVERS[package.package_hash] = (CapturedFontResolver(package), {})
        while len(_RESOLVERS) > 4:
            _RESOLVERS.pop(next(iter(_RESOLVERS)))
    return found


def style_key(ref):
    overrides = ref.overrides.model_dump(mode='json', by_alias=True)
    if not any(value is not None for value in overrides.values()):
        return ref.style_token
    return ref.style_token + '~' + sha256(canonical(overrides))[:12]


def utf16_len(text):
    """Editor offsets are UTF-16 code units, the same length a JavaScript string reports."""
    return len(text.encode('utf-16-le')) // 2


def literal_key(start, end):
    """A literal has no binding id. The editor paints this range; a field or scope keeps its own key."""
    return f'literal@{start}@{end}'


def style_entry(package, fonts, ref):
    """Size, line height, color and the captured face for each mark combination; a missing face is None."""
    from ..rendering.captured_fonts import FontRequest
    from ..rendering.captured_styles import scaled_line_height
    from ..rendering.template import RenderFailure
    style, overrides = package.recipe.style.text[ref.style_token], ref.overrides
    size = overrides.size if overrides.size is not None else style.size
    faces = {}
    for name, bold, italic in [('regular', False, False), ('bold', True, False), ('italic', False, True), ('boldItalic', True, True)]:
        try:
            faces[name] = fonts.select(FontRequest(overrides.font or style.font, bold=overrides.bold, italic=overrides.italic,
                mark_bold=bold, mark_italic=italic)).font.asset_id
        except RenderFailure:
            faces[name] = None
    try:
        # An italic base font names its upright face too: the editor slants it for the letters the italic face lacks, as
        # the DOCX does.
        base = fonts.select(FontRequest(overrides.font or style.font, bold=overrides.bold, italic=overrides.italic))
        if base.italic:
            faces['upright'] = fonts.select(FontRequest(overrides.font or style.font, bold=overrides.bold, italic=False)).font.asset_id
    except RenderFailure:
        pass
    return {'faces': faces, 'size': size, 'lineHeight': scaled_line_height(style.line_height, size, style.size),
        'color': overrides.color or package.recipe.style.colors[style.color], 'alignment': overrides.alignment or style.alignment}


def editor_plan(project):
    """Per block: its style, band, Focus icon and technology chips, and which bound links export as hyperlinks; the
    places the facts panel can add a technology and whether it can change Focus rows."""
    package = project.template_package
    recipe = package.recipe
    fonts, styles = resolver(package)
    blocks, files = {}, {}
    rows = table_rows(project.document, recipe, package.definition.template.default_locale)
    def keyed(ref):
        key = style_key(ref)
        if key not in styles:
            styles[key] = style_entry(package, fonts, ref)
        return key
    for block in project.document.blocks():
        ref = block.presentation
        entry = {'style': keyed(ref)}
        if is_band(block, recipe):
            entry['band'] = True
        row = rows.get(block.id)
        if row is not None:
            # The row's own style is its label's: the section shows no text, and the editor draws the label from it.
            entry['row'] = row
            entry['style'] = keyed(ref.model_copy(update={'style_token': recipe.style.tables[row['table']].label_style}, deep=True))
        row = focus_row(block, recipe)
        if row:
            icon = row_icon(package, project.facts, row, catalog_for(package), block.props.icon)
            entry['focus'] = {'blocks': [child.id for child in row], 'icon': icon[0] if icon else None}
            if icon:
                files[icon[0]] = icon[1]
        inline, links, chips, offset = {}, [], {}, 0
        for span in block.content if isinstance(block.content, list) else []:
            for part in span.content if span.type == 'bound_link' else [span]:
                identity = getattr(part, 'binding_id', None) or getattr(part, 'fragment_id', None)
                if identity is not None and part.presentation is not None and style_key(part.presentation) != entry['style']:
                    inline[identity] = keyed(part.presentation)
            chip = chip_background(block, span, recipe)
            if chip is not None:
                chips[getattr(span, 'binding_id', None) or span.fragment_id] = chip
            if span.type == 'bound_link' and hyperlink_target(span.href) is not None:
                links.append((span.label_binding or span.url_binding).occurrence_id)
        # A literal span has no node id. Record its UTF-16 range when its style is not the block's.
        if isinstance(block.content, list):
            for span, _link in authored_spans(block):
                text = span.text or ''
                identity = getattr(span, 'binding_id', None) or getattr(span, 'fragment_id', None)
                if identity is None and span.presentation is not None and text and style_key(span.presentation) != entry['style']:
                    end = offset + utf16_len(text)
                    inline[literal_key(offset, end)] = keyed(span.presentation)
                offset += utf16_len(text)
        if inline:
            entry['inline'] = inline
        if links:
            entry['links'] = links
        if chips:
            entry['chips'] = chips
        blocks[block.id] = entry
    used = {styles[value['style']]['faces'][face] for value in blocks.values() for face in ('regular', 'bold', 'italic', 'boldItalic')}
    used |= {face for key in {key for value in blocks.values() for key in value.get('inline', {}).values()}
        for face in styles[key]['faces'].values()}
    icons = sorted(files)
    for icon, asset in files.items():
        # A packed or generated icon is no asset of its own; its checked bytes join the captured ones the asset
        # route serves by hash.
        remember_asset(asset.sha256, asset.bytes_base64, asset.mime_type)
    files = {icon: files[icon].sha256 for icon in icons}
    plan = {'styles': {key: styles[key] for key in sorted({value['style'] for value in blocks.values()}
            | {key for value in blocks.values() for key in value.get('inline', {}).values()})},
        'blocks': blocks, 'fonts': sorted(face for face in used if face is not None), 'icons': icons}
    if files:
        plan['iconFiles'] = files
    from ..editing.template_panel_focus import focus_full, focus_only
    from ..editing.template_panel_records import panel_plan, technology_targets
    targets = [value.model_dump(mode='json', by_alias=True) for value in technology_targets(project)]
    if targets:
        plan['technologyTargets'] = targets
    plan.update(panel_plan(project))
    only = focus_only(project)
    if only is not None:
        plan['focusPanel'] = {'records': sorted(only), **({'full': True} if focus_full(project) else {})}
        # A row's icon can be chosen from the template's icons (D122); a template without them offers no choice.
        if catalog_for(package).files:
            plan['focusPanel']['icons'] = True
    return plan
