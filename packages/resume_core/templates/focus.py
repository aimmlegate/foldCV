"""Decorative Focus icons: the template's captured alias catalog names an icon for a technology."""

import base64
import binascii
import json
import math

from ..dates import month_bounds, union_months
from ..rich_fields import records_by_id, working_field
from ..technologies import normalize_name, technology_identity
from ..technology_experience import whole_years_text
from .projection import pointer_tokens


def icon_catalog(package):
    """Normalized alias to captured icon asset; empty when the template declares no catalog."""
    name = package.recipe.style.focus.icon_catalog
    if name is None:
        return {}
    assets = {asset.id: asset for asset in package.assets}
    try:
        aliases = json.loads(base64.b64decode(assets[name].bytes_base64, validate=True))
    except (KeyError, binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError('focus icon catalog is unreadable') from None
    if not isinstance(aliases, dict) or not all(isinstance(alias, str) and isinstance(icon, str)
            and icon in assets and assets[icon].role == 'icon' for alias, icon in aliases.items()):
        raise ValueError('focus icon catalog names an unknown icon')
    return {normalize_name(alias): icon for alias, icon in aliases.items()}


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


def focus_icon(package, facts, row, catalog=None):
    """The icon of one Focus row from the current text of its first bound name field; None shows text only."""
    catalog = icon_catalog(package) if catalog is None else catalog
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
                    return catalog.get(normalize_name(field.raw_text)) if field is not None else None
    return None


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
