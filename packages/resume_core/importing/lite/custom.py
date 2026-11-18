"""A template's own block: one the scheme has no request of its own for.

Its shape is the block's schema in the template. The reply asked of the model follows it with two changes: every text
may be null, and a date is given as the text the line writes (code reads the year). Code then copies the reply into
the block's shape and keeps a value only when the block's lines state it, as for every other block."""

from . import prompts as P

DATE = {'raw', 'year', 'month'}


def resolved(root, node):
    """A schema node with its reference followed (the template's content definitions stand under $defs)."""
    while isinstance(node, dict) and '$ref' in node:
        node = root.get('$defs', {}).get(node['$ref'].rsplit('/', 1)[-1], {})
    return node if isinstance(node, dict) else {}


def kinds(node):
    found = node.get('type')
    return set(found) if isinstance(found, list) else {found} if found else set()


def is_date(node):
    return 'object' in kinds(node) and set(node.get('properties') or {}) == DATE


def asked(schema):
    """The reply schema of a block's call, and whether the block's content is a list (then it stands under items:
    a reply is an object)."""
    def walk(node):
        node = resolved(schema, node)
        types = kinds(node)
        if is_date(node):
            return P.TEXT
        if 'array' in types:
            return P.array(walk(node.get('items') or {}))
        if 'object' in types:
            body = P.closed({key: walk(value) for key, value in (node.get('properties') or {}).items()})
            return {**body, 'type': ['object', 'null']} if 'null' in types else body
        if 'enum' in node:
            return {'type': sorted(types - {'null'} | {'null'}), 'enum': [*[value for value in node['enum'] if value is not None], None]}
        for name in ('integer', 'number', 'boolean'):
            if name in types:
                return {'type': [name, 'null']}
        return P.TEXT
    listed = 'array' in kinds(resolved(schema, schema))
    root = walk(schema)
    return (P.closed({'items': root}) if listed else root), listed


def blank(value):
    if isinstance(value, dict):
        return all(blank(part) for part in value.values())
    if isinstance(value, (list, tuple)):
        return not value
    return value is None or isinstance(value, str) and not value.strip()


def described(block):
    """What a template's block holds, in its author's words: its title and its first instruction."""
    # By locale name, so the same template gives the same words whatever order its file or its saved copy has.
    titles = ' / '.join(dict.fromkeys(text for _locale, text in sorted((block.view.title or {}).items()) if text))
    first = next(iter([*block.extract, *block.rules]), '')
    return ' — '.join(part for part in (titles or block.id, first) if part)
