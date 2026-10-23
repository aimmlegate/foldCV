"""One presentation plan for the mounted editor and the DOCX writer: decisions Python makes from the captured package."""

from urllib.parse import urlsplit

from .compiler import canonical, sha256
from .focus import focus_icon, icon_catalog


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


def node_of(recipe, ref):
    return recipe.views[ref.view_key].nodes[ref.node_index] if ref is not None and ref.node_index is not None else None


def is_band(block, recipe):
    """A view title heading in a view whose compiled heading is a band; never inferred from wording or IDs."""
    ref = block.presentation
    return (block.type == 'heading' and ref is not None and ref.node_index is None
        and recipe.views[ref.view_key].heading == 'band')


def focus_row(block, recipe):
    """The leading Focus paragraphs of an item section; they share one decorative icon row."""
    row = []
    for child in block.children if block.type == 'section' else []:
        node = node_of(recipe, child.presentation)
        if child.type != 'paragraph' or child.children or node is None or node.type != 'focus_entry':
            break
        row.append(child)
    return row


_RESOLVERS = {}


def resolver(package):
    from ..rendering.captured_fonts import CapturedFontResolver
    found = _RESOLVERS.get(package.package_hash)
    if found is None:
        found = _RESOLVERS[package.package_hash] = (CapturedFontResolver(package), {}, [None])
        while len(_RESOLVERS) > 4:
            _RESOLVERS.pop(next(iter(_RESOLVERS)))
    return found


def style_key(ref):
    overrides = ref.overrides.model_dump(mode='json', by_alias=True)
    if not any(value is not None for value in overrides.values()):
        return ref.style_token
    return ref.style_token + '~' + sha256(canonical(overrides))[:12]


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
    return {'faces': faces, 'size': size, 'lineHeight': scaled_line_height(style.line_height, size, style.size),
        'color': overrides.color or package.recipe.style.colors[style.color], 'alignment': overrides.alignment}


def editor_plan(project):
    """Per block: its style, band and Focus icon, and which bound links export as hyperlinks."""
    package = project.template_package
    recipe = package.recipe
    fonts, styles, cached = resolver(package)
    blocks = {}
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
        row = focus_row(block, recipe)
        if row:
            if cached[0] is None:
                cached[0] = icon_catalog(package)
            entry['focus'] = {'blocks': [child.id for child in row], 'icon': focus_icon(package, project.facts, row, cached[0])}
        inline, links = {}, []
        for span in block.content if isinstance(block.content, list) else []:
            for part in span.content if span.type == 'bound_link' else [span]:
                identity = getattr(part, 'binding_id', None) or getattr(part, 'fragment_id', None)
                if identity is not None and part.presentation is not None and style_key(part.presentation) != entry['style']:
                    inline[identity] = keyed(part.presentation)
            if span.type == 'bound_link' and hyperlink_target(span.href) is not None:
                links.append((span.label_binding or span.url_binding).occurrence_id)
        if inline:
            entry['inline'] = inline
        if links:
            entry['links'] = links
        blocks[block.id] = entry
    used = {styles[value['style']]['faces'][face] for value in blocks.values() for face in ('regular', 'bold', 'italic', 'boldItalic')}
    used |= {face for key in {key for value in blocks.values() for key in value.get('inline', {}).values()}
        for face in styles[key]['faces'].values()}
    icons = {value['focus']['icon'] for value in blocks.values() if value.get('focus')}
    return {'styles': {key: styles[key] for key in sorted({value['style'] for value in blocks.values()}
            | {key for value in blocks.values() for key in value.get('inline', {}).values()})},
        'blocks': blocks, 'fonts': sorted(face for face in used if face is not None),
        'icons': sorted(icon for icon in icons if icon is not None)}
