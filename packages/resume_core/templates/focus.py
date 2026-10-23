"""Decorative Focus icons: the template's captured alias catalog names an icon for a technology."""

import base64
import binascii
import json

from ..rich_fields import records_by_id, working_field
from ..technologies import normalize_name
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
