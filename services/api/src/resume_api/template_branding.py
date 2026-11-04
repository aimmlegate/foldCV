"""«Шаблоны»: a template's own logo in its logo place and an optional footer email (D145).

A change is a new revision of the template: its text gets the values by node marks, so comments and layout stay, and its
package captures the logo as `assets/logo.png`. Projects keep the package they captured.
"""

import base64
import binascii
from io import BytesIO
import json
import re

from PIL import Image, UnidentifiedImageError
from pydantic import Field
import yaml
from yaml.nodes import MappingNode, ScalarNode

from packages.resume_core.models.contracts import Wire
from packages.resume_core.rich_limits import IMAGE_PIXELS

LOGO_ID, LOGO_PATH = 'logo', 'assets/logo.png'
LOGO_BYTES = 2 * 1024 * 1024
# Four times the widest logo place at 72 dpi stays sharp in print; larger pictures only grow the package.
LOGO_SIDE = 1200
EMAIL = re.compile(r'[^\s@]+@[^\s@.]+(\.[^\s@.]+)+')
FOOTER_CHARS = 254

NO_PLACE = 'В этом шаблоне нет места для логотипа.'
NOT_IMAGE = 'Нужна картинка PNG, JPEG или WebP.'
TOO_LARGE = 'Файл логотипа больше 2 МБ.'
NOT_EMAIL = 'Укажите email, например hr@company.com, или оставьте поле пустым.'
NOT_EDITABLE = 'Шаблон записан в форме, которую здесь не изменить. Измените его YAML.'


class BrandingRefused(Exception):
    def __init__(self, path, message):
        super().__init__(message)
        self.path, self.message = path, message


class TemplateBrandingRequest(Wire):
    # The new logo: PNG, JPEG or WebP bytes in base64. Without it `remove_logo` empties the place, else the logo stays.
    logo: str | None = Field(default=None, max_length=(LOGO_BYTES * 4) // 3 + 4)
    remove_logo: bool = False
    footer: str = Field(max_length=FOOTER_CHARS)


def logo_png(encoded):
    """The upload as a PNG of at most LOGO_SIDE pixels a side; BrandingRefused for anything else."""
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise BrandingRefused('/logo', NOT_IMAGE) from None
    if len(data) > LOGO_BYTES:
        raise BrandingRefused('/logo', TOO_LARGE)
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in {'PNG', 'JPEG', 'WEBP'} or image.width * image.height > IMAGE_PIXELS:
                raise ValueError('unsupported image')
            image.load()
            picture = image.convert('RGBA')
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise BrandingRefused('/logo', NOT_IMAGE) from None
    picture.thumbnail((LOGO_SIDE, LOGO_SIDE))
    out = BytesIO()
    picture.save(out, 'PNG', optimize=True)
    return out.getvalue()


def footer_text(value):
    text = value.strip()
    if text and not EMAIL.fullmatch(text):
        raise BrandingRefused('/footer', NOT_EMAIL)
    return text


def branding(package):
    """What «Шаблоны» shows: whether the template has a logo place, its logo as a data URL, and its footer text."""
    style = package.recipe.style
    place = style.header.logo
    asset = next((value for value in package.assets if place is not None and value.id == place.asset), None)
    return {'logoPlace': place is not None,
        'logo': f'data:{asset.mime_type};base64,{asset.bytes_base64}' if asset is not None else None,
        'footer': style.footer.text}


def _pair(mapping, key):
    return next(((name, value) for name, value in mapping.value if isinstance(name, ScalarNode) and name.value == key), None)


def _mapping(root, path):
    node = root
    for key in path:
        pair = _pair(node, key) if isinstance(node, MappingNode) else None
        if pair is None:
            return None
        node = pair[1]
    return node if isinstance(node, MappingNode) else None


def _span_lines(text, start, end):
    """[start of `start`'s line, end of the line holding `end`); a block value ending at the next line's indent stops there."""
    first = text.rfind('\n', 0, start) + 1
    line = text.rfind('\n', 0, end) + 1
    if line > first and not text[line:end].strip():
        return first, line
    stop = text.find('\n', end)
    return first, len(text) if stop < 0 else stop + 1


def edited_yaml(text, changes):
    """`text` with `changes` ((path, value) pairs) applied by node marks: a string sets the key to that YAML, None removes
    it; a missing key joins its block mapping first. None when a parent is missing or written in flow style."""
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError):
        return None
    edits = []
    for path, value in changes:
        parent = _mapping(root, path[:-1])
        if parent is None or parent.flow_style:
            return None
        pair = _pair(parent, path[-1])
        if pair is not None and value is not None and isinstance(pair[1], ScalarNode):
            start, end = pair[1].start_mark.index, pair[1].end_mark.index
            # An empty plain value (`key:`) has no span of its own.
            edits.append((start, end, value if start != end or text[start - 1:start] in (' ', '\t') else ' ' + value))
            continue
        if pair is not None:
            start, end = _span_lines(text, pair[0].start_mark.index, pair[1].end_mark.index)
            edits.append((start, end, ''))
        if value is None:
            continue
        if not parent.value:
            return None
        first = parent.value[0][0].start_mark
        line = text.rfind('\n', 0, first.index) + 1
        ending = '\r\n' if '\r\n' in text else '\n'
        edits.append((line, line, f'{text[line:first.index]}{path[-1]}: {value}{ending}'))
    for start, end, replacement in sorted(edits, key=lambda edit: (edit[0], edit[1]), reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def edited_json(text, changes):
    """The same edits on a JSON template: it has no comments to keep, so it is written again with two-space indents."""
    try:
        value = json.loads(text)
    except ValueError:
        return None
    for path, change in changes:
        parent = value
        for key in path[:-1]:
            parent = parent.get(key) if isinstance(parent, dict) else None
        if isinstance(parent, list) and path[:-1] == ('assets',):
            # The expanded form lists asset declarations by id; the only one added here is the PNG logo.
            parent[:] = [item for item in parent if not (isinstance(item, dict) and item.get('id') == path[-1])]
            if change is not None:
                parent.append({'id': path[-1], **yaml.safe_load(change), 'mime_type': 'image/png', 'embedding': 'not_applicable'})
            continue
        if not isinstance(parent, dict):
            return None
        if change is None:
            parent.pop(path[-1], None)
        else:
            parent[path[-1]] = yaml.safe_load(change)
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def changes(package, logo, remove_logo, footer):
    """The text edits of one branding save, and whether the package then holds the new logo."""
    place = package.recipe.style.header.logo
    edits = [(('style', 'footer', 'text'), json.dumps(footer, ensure_ascii=False))]
    if logo is None and not remove_logo:
        return edits
    if place is None:
        raise BrandingRefused('/logo', NO_PLACE)
    # The old logo's declaration goes with it, whatever its id; the new one is always `logo`.
    if place.asset is not None and place.asset != LOGO_ID:
        edits.append((('assets', place.asset), None))
    if logo is None:
        edits += [(('style', 'header', 'logo', 'asset'), None), (('assets', LOGO_ID), None)]
    else:
        edits += [(('style', 'header', 'logo', 'asset'), LOGO_ID), (('assets', LOGO_ID), f'{{path: {LOGO_PATH}, role: logo}}')]
    return edits
