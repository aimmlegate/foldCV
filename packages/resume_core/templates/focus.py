"""Decorative Focus icons: the template's captured alias catalog names an icon for a technology."""

import base64
import binascii
from dataclasses import dataclass, field
import hashlib
import json
import math
import re
import threading

from ..dates import month_bounds, union_months
from ..rich_fields import records_by_id, working_field
from ..technologies import BY_ID, normalize_name, resolve_technology, split_version, technology_identity
from ..technology_experience import whole_years_text
from .models import CapturedAsset
from .projection import pointer_tokens

_QUALIFIER = re.compile(r'\s*\([^()]*\)$')
PACK = 'foldcv-icon-pack-1'


@dataclass(frozen=True)
class IconCatalog:
    """The template's names for its icons, the same icons by technology catalog ID, and each icon's PNG."""
    aliases: dict[str, str] = field(default_factory=dict)
    canonical: dict[str, str] = field(default_factory=dict)
    files: dict[str, CapturedAsset] = field(default_factory=dict)

    def find(self, text):
        """The template's own name wins; then the catalog technology the name resolves to (k8s, Python 3.12,
        GitLab CI/CD); a trailing parenthetical qualifier is dropped last. None shows text only."""
        name = normalize_name(text)
        for candidate in dict.fromkeys(value for value in (name, _QUALIFIER.sub('', name)) if value):
            icon = (self.aliases.get(candidate) or self.aliases.get(split_version(candidate)[0])
                or self.canonical.get(resolve_technology(candidate).canonical_id))
            if icon is not None:
                return icon
        return None


def packed_icons(catalog, icons):
    """The PNGs an icon pack carries, as icon assets of the catalog asset; each is checked against its stated hash."""
    if not isinstance(icons, dict):
        raise ValueError('focus icon catalog is unreadable')
    files = {}
    for icon, value in icons.items():
        if not isinstance(value, dict) or not isinstance(value.get('png'), str) or not isinstance(value.get('sha256'), str):
            raise ValueError('focus icon catalog is unreadable')
        try:
            raw = base64.b64decode(value['png'], validate=True)
        except binascii.Error:
            raise ValueError('focus icon catalog is unreadable') from None
        if hashlib.sha256(raw).hexdigest() != value['sha256']:
            raise ValueError('focus icon catalog is unreadable')
        files[icon] = CapturedAsset(id=icon, path=catalog.path + '#' + icon, role='icon', mimeType='image/png',
            sha256=value['sha256'], size=len(raw), bytesBase64=value['png'])
    return files


def icon_catalog(package):
    """The captured alias catalog of the template; empty when the template declares none. A flat catalog names icon
    assets; an icon pack (one asset, as a portable archive holds at most 47 entries) carries names and PNGs."""
    name = package.recipe.style.focus.icon_catalog
    if name is None:
        return IconCatalog()
    assets = {asset.id: asset for asset in package.assets}
    try:
        aliases = json.loads(base64.b64decode(assets[name].bytes_base64, validate=True))
    except (KeyError, binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError('focus icon catalog is unreadable') from None
    if isinstance(aliases, dict) and aliases.get('schema') == PACK:
        files = packed_icons(assets[name], aliases.get('icons'))
        aliases = aliases.get('names')
    else:
        files = {asset.id: asset for asset in package.assets if asset.role == 'icon'}
    if not isinstance(aliases, dict) or not all(isinstance(alias, str) and isinstance(icon, str) and icon in files
            for alias, icon in aliases.items()):
        raise ValueError('focus icon catalog names an unknown icon')
    normalized = {normalize_name(alias): icon for alias, icon in aliases.items()}
    # A key that is a catalog ID binds it first; older packages name icons by display aliases only (c#, .net).
    canonical = {alias: icon for alias, icon in normalized.items() if alias in BY_ID}
    for alias, icon in normalized.items():
        identifier = resolve_technology(alias).canonical_id
        if identifier is not None:
            canonical.setdefault(identifier, icon)
    return IconCatalog(normalized, canonical, files)


_CATALOGS, _CATALOG_LOCK = {}, threading.Lock()


def catalog_for(package):
    """`icon_catalog` decoded once for the latest few packages: the Generic pack is 6.8 MB. Replies, edits and the
    icon search run in worker threads. A catalog captured unreadable has no icons, so its rows stay text only; new
    packages refuse it at compile."""
    with _CATALOG_LOCK:
        found = _CATALOGS.get(package.package_hash)
    if found is None:
        try:
            found = icon_catalog(package)
        except ValueError:
            found = IconCatalog()
        with _CATALOG_LOCK:
            _CATALOGS[package.package_hash] = found
            while len(_CATALOGS) > 4:
                _CATALOGS.pop(next(iter(_CATALOGS)))
    return found


def remembered_catalog(remembered):
    """The icons the user chose before (D122), by normalized name and by the catalog technology a name resolves to;
    the later choice wins. Its `find` matches a row name as the template's own names do."""
    canonical = {}
    for name, icon in remembered.items():
        identifier = resolve_technology(name).canonical_id
        if identifier is not None:
            canonical[identifier] = icon
    return IconCatalog(dict(remembered), canonical)


def remembered_icon(catalog, remembered, name):
    """The icon remembered for a row name when this package has it; None keeps the package's own choice."""
    found = remembered.find(name) if remembered is not None and name else None
    return found if found is not None and found in catalog.files else None


def name_keys(definition, view_key, node):
    """Cell keys of the field a Focus node shows as its name, builtin mappings included."""
    block = next(value for value in definition.blocks if value.id == view_key)
    types = {value.id: value for value in definition.fact_types}
    path = (['*'] if block.view.mode == 'items' else []) + pointer_tokens(node.name_field)
    keys = set()
    for binding in block.bindings:
        if pointer_tokens(binding.pointer) == path:
            mapped = types[binding.semantic_type].builtin_fields.get(binding.field)
            keys.add(mapped.field if mapped is not None else binding.field)
    return keys


def row_name(package, facts, row):
    """The current text of the first bound name field of one Focus row; None when it shows no bound name."""
    records = records_by_id(facts)
    for block in row:
        ref = block.presentation
        if ref is None or ref.node_index is None:
            continue
        node = package.recipe.views[ref.view_key].nodes[ref.node_index]
        keys = name_keys(package.definition, ref.view_key, node)
        for span in block.content:
            for part in span.content if span.type == 'bound_link' else [span]:
                if part.type == 'fact_field' and part.field_key in keys and part.record_id in records:
                    field = working_field(records[part.record_id], part.field_key)
                    return field.raw_text if field is not None else None
    return None


_INITIALS = {}
INITIAL_SIDE = 160
INITIAL_BACKGROUND = (0xEF, 0xEF, 0xEF, 0xFF)
INITIAL_INK = (0x80, 0x80, 0x80, 0xFF)


def initial_icon(package, row, name):
    """The placeholder of a row without an icon: a grey square with the name's first letter or digit in the row's font
    (D113). None keeps the row text-only: for a text_only template, a name without one, or an unreadable font."""
    if package.recipe.style.focus.missing_icon != 'initial' or not name:
        return None
    letter = next((character.upper() for character in name if character.isalnum()), None)
    ref = row[0].presentation if row else None
    if letter is None or ref is None:
        return None
    token = package.recipe.style.text[ref.style_token].font
    key = (package.package_hash, token, letter)
    if key not in _INITIALS:
        fonts = {asset.id: asset for asset in package.assets}
        try:
            raw = _initial_png(base64.b64decode(fonts[package.recipe.style.fonts[token]].bytes_base64), letter)
        except (KeyError, OSError, ValueError):
            raw = None
        digest = hashlib.sha256(raw).hexdigest() if raw is not None else None
        _INITIALS[key] = None if raw is None else CapturedAsset(id='initial-' + digest[:24], path='generated#' + digest,
            role='icon', mimeType='image/png', sha256=digest, size=len(raw), bytesBase64=base64.b64encode(raw).decode('ascii'))
    return _INITIALS[key]


def _initial_png(font_bytes, letter):
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(BytesIO(font_bytes), round(INITIAL_SIDE * .6))
    image = Image.new('RGBA', (INITIAL_SIDE, INITIAL_SIDE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, INITIAL_SIDE - 1, INITIAL_SIDE - 1), radius=INITIAL_SIDE // 6, fill=INITIAL_BACKGROUND)
    # Centered by the drawn glyph, not the font's line box, so Q and k sit as high as H.
    left, top, right, bottom = draw.textbbox((0, 0), letter, font=font)
    draw.text(((INITIAL_SIDE - right - left) / 2, (INITIAL_SIDE - bottom - top) / 2), letter, font=font, fill=INITIAL_INK)
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def row_icon(package, facts, row, catalog=None, chosen=None):
    """The icon a Focus row shows as (key, PNG asset): the one the user chose for it (D122), else the catalog's, else
    the template's placeholder; None shows text only. Editor and DOCX use this one decision."""
    catalog = icon_catalog(package) if catalog is None else catalog
    if chosen is not None and chosen in catalog.files:
        return chosen, catalog.files[chosen]
    name = row_name(package, facts, row)
    found = catalog.find(name) if name is not None else None
    if found is not None:
        return found, catalog.files[found]
    placeholder = initial_icon(package, row, name)
    return (placeholder.id, placeholder) if placeholder is not None else None


def duration_text(months, locale):
    """Whole years from a year on, months below it, as the Generic examples write them (6 лет, 10 месяцев)."""
    if months <= 0:
        return None
    russian = locale == 'ru'
    if months >= 12:
        return whole_years_text(math.floor(months / 12 + .5), russian)
    if not russian:
        return f'{months} month' + ('s' if months != 1 else '')
    noun = 'месяцев' if 11 <= months % 100 <= 14 else 'месяц' if months % 10 == 1 else 'месяца' if 2 <= months % 10 <= 4 else 'месяцев'
    return f'{months} {noun}'


def focus_durations(facts, as_of, locale):
    """Technology record id to the time the jobs listing that technology span (D104: the user chose durations counted
    from projects when the CV states none). Overlaps count once, an ongoing job runs to the formatting date, and a
    period without a known start or end is left out; partial dates count the middle of their range."""
    jobs = {record.id: record for record in facts.records if record.kind in {'employment', 'subproject'}}
    groups, owners = {}, {}
    for record in facts.records:
        if record.kind != 'technology':
            continue
        key = technology_identity(record)
        groups.setdefault(key, []).append(record.id)
        owner = record.subproject_id or record.job_id
        if owner in jobs:
            owners.setdefault(key, set()).add(owner)
    now = month_bounds(as_of)[0]
    result = {}
    for key, linked in owners.items():
        lower, upper = [], []
        for period in (period for owner in sorted(linked) for period in jobs[owner].periods):
            if period.start.status != 'known' or period.start.value is None:
                continue
            if period.present.status == 'known' and period.present.value is True:
                end = (now, now)
            elif period.end.status == 'known' and period.end.value is not None:
                end = month_bounds(period.end.value)
            else:
                continue
            start = month_bounds(period.start.value)
            lower.append((start[1], end[0]))
            upper.append((start[0], end[1]))
        text = duration_text(math.floor((union_months(lower) + union_months(upper)) / 2 + .5), locale) if upper else None
        if text is not None:
            result.update({identifier: text for identifier in groups[key]})
    return result
