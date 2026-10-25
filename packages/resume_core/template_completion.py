"""Protocol 5: the coordinator completes the bookkeeping a reply's payload implies.

A reply states the payload and the evidence of its values. Which item a value belongs to, the add lineage of new
items and the relations the template configures follow from payload pointers and the compiled bindings, so they
are derived here when the reply leaves them out or names them inconsistently. A value copied word for word from
an offered entry cites the narrowest entries that contain it. What cannot be derived stays missing, and the
existing checks refuse it with the binding named: a value with no evidence, a selection the request did not offer,
an explicit split or merge that names unknown items.
"""

import re

from .template_identity import _binding_instances, _bound_root, empty_value, payload_value
from .templates.projection import pointer_tokens

# A derived value cites at most this many offered entries; each states it word for word.
STATED_LIMIT = 3


def pointer_of(tokens):
    return ''.join('/' + token.replace('~', '~0').replace('/', '~1') for token in tokens)


def _natural(pointer):
    return [(0, int(token), '') if token.isdecimal() else (1, 0, token) for token in pointer_tokens(pointer)]


def _inside(inner, outer):
    same = (inner.source_id, inner.source_revision, inner.unit_id, inner.unit_revision) == (
        outer.source_id, outer.source_revision, outer.unit_id, outer.unit_revision)
    return same and outer.start <= inner.start and inner.end <= outer.end and (inner.start, inner.end) != (outer.start, outer.end)


def stated_text(payload, pointer):
    """The source wording a value carries: a string, or the raw text of the date or period it belongs to."""
    value = payload_value(payload, pointer)
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict) and isinstance(value.get('raw'), str):
        return value['raw'].strip() or None
    tokens = pointer_tokens(pointer)
    if isinstance(value, (bool, int, float)) and tokens:
        parent = payload_value(payload, pointer_of(tokens[:-1]))
        if isinstance(parent, dict) and isinstance(parent.get('raw'), str):
            return parent['raw'].strip() or None
    return None


def stating(text, table):
    """Refs of the narrowest offered entries that contain the text word for word."""
    pattern = re.compile(r'(?<!\w)' + re.escape(text) + r'(?!\w)')
    hits = [option for option in table.values() if pattern.search(option.text)]
    narrow = [option for option in hits if not any(other is not option and _inside(other.span, option.span) for other in hits)]
    return [option.ref for option in narrow[:STATED_LIMIT]]


def complete_reply(reply, bindings, table, references):
    """The referenced reply with derived fields entries, item selections, discoveries, add lineage and relations."""
    if not isinstance(reply, dict) or not bindings:
        return reply
    payload = reply.get('payload')
    instances = {}
    for pointer, semantic, field in _binding_instances(payload, bindings):
        instances.setdefault(pointer, []).append((semantic, field))
    def under(pointer, ancestor):
        tokens, parent = pointer_tokens(pointer), pointer_tokens(ancestor)
        return len(tokens) > len(parent) and tokens[:len(parent)] == parent
    # An entry at a list or object pointer that holds bound values gives its evidence to those values.
    entries, providers = [], {}
    for given in reply.get('fields') or []:
        entry = dict(given)
        pointer = entry.get('pointer')
        matches = instances.get(pointer, [])
        if entry.get('fieldKey') is None and len(matches) == 1:
            entry['fieldKey'] = matches[0][1]
        if not matches and isinstance(pointer, str) and any(under(candidate, pointer) for candidate in instances):
            providers[pointer] = list(entry.get('evidence') or [])
            continue
        if entry.get('effectiveCells') is None:
            entry['effectiveCells'] = []
        entries.append(entry)
    def derived_evidence(pointer):
        if empty_value(payload_value(payload, pointer)):
            return []
        ancestors = sorted((value for value in providers if under(pointer, value) and providers[value]), key=len)
        if ancestors:
            return providers[ancestors[-1]]
        text = stated_text(payload, pointer)
        return (stating(text, table) or None) if text else None
    given = {(entry.get('pointer'), entry.get('fieldKey')) for entry in entries}
    for pointer in sorted(instances, key=_natural):
        for _semantic, field in instances[pointer]:
            if (pointer, field) in given:
                continue
            evidence = derived_evidence(pointer)
            if evidence is not None:
                entries.append({'item': None, 'fieldKey': field, 'pointer': pointer, 'evidence': evidence, 'effectiveCells': []})
    for entry in entries:
        if not entry.get('evidence') and not entry.get('effectiveCells') and entry.get('pointer') in instances:
            entry['evidence'] = derived_evidence(entry['pointer']) or []
    # Each value belongs to the item its binding's item pointer names; new items are named by that root.
    def root_of(entry):
        pointer, key = entry.get('pointer'), entry.get('fieldKey')
        semantic = next((semantic for semantic, field in instances.get(pointer, []) if field == key), None)
        return None if semantic is None else (semantic, pointer_of(_bound_root(pointer, semantic, key, bindings)))
    roots = {}
    for entry in entries:
        root = root_of(entry)
        if root is not None:
            roots.setdefault(root, []).append(entry)
    discoveries = [dict(value) for value in reply.get('discoveries') or []]
    declared = {}
    for value in discoveries:
        identity = (value.get('semanticType'), value.get('pointer'))
        if identity in roots and identity not in declared:
            declared[identity] = value.get('key')
    handles = {root: {entry['item'].get('ref') for entry in values if isinstance(entry.get('item'), dict)
        and entry['item'].get('kind') == 'handle'} for root, values in roots.items()}
    taken = {value.get('key') for value in discoveries}
    keys, added = {}, []
    for root in sorted(roots, key=lambda value: (_natural(value[1]), value[0])):
        if handles[root]:
            continue
        key = declared.get(root)
        if key is None:
            key = 'auto' + root[1] + '@' + root[0]
            while key in taken:
                key += '+'
            taken.add(key)
            added.append({'key': key, 'semanticType': root[0], 'pointer': root[1]})
        keys[root] = key
    for root, values in roots.items():
        for entry in values:
            if root in keys:
                entry['item'] = {'kind': 'discovery_key', 'key': keys[root]}
            elif len(handles[root]) == 1 and entry.get('item') is None:
                entry['item'] = {'kind': 'handle', 'ref': next(iter(handles[root]))}
    used = set(keys.values())
    discoveries = [value for value in discoveries if value.get('key') in used] + added
    # Split and merge stay explicit; every other new item is added.
    explicit = [dict(value) for value in reply.get('lineage') or [] if value.get('kind') in {'split', 'merge'}]
    children = {child for value in explicit for child in value.get('children') or []}
    new = [value['key'] for value in discoveries if value['key'] not in children]
    lineage = explicit + ([{'kind': 'add', 'parents': [], 'children': new}] if new else [])
    return {**reply, 'fields': entries, 'discoveries': discoveries, 'lineage': lineage,
        'relations': _relations(reply, entries, roots, keys, handles, instances, bindings, references)}


def _relations(reply, entries, roots, keys, handles, instances, bindings, references):
    """Model relations between final items, plus each configured relation the reply left out or aimed elsewhere."""
    def selector(root):
        if root in keys:
            return {'kind': 'discovery_key', 'key': keys[root]}
        if root in handles and len(handles[root]) == 1:
            return {'kind': 'handle', 'ref': next(iter(handles[root]))}
        return None
    final = [selector(root) for root in roots]
    def identity(value):
        return (value.get('kind'), value.get('key') if value.get('kind') == 'discovery_key' else value.get('ref')) \
            if isinstance(value, dict) else None
    selectable = {identity(value) for value in final if value is not None}
    configured = {}
    for entry in entries:
        actual = pointer_tokens(entry['pointer']) if isinstance(entry.get('pointer'), str) else None
        root = next((root for root, values in roots.items() if any(value is entry for value in values)), None)
        if actual is None or root is None:
            continue
        for binding in bindings:
            pattern = pointer_tokens(binding.pointer)
            if (binding.semantic_type != root[0] or binding.field != entry.get('fieldKey') or binding.relation is None
                    or binding.item_pointer is None or len(pattern) != len(actual)
                    or any(expected not in {'*', value} for expected, value in zip(pattern, actual))):
                continue
            target = [actual[index] if token == '*' and index < len(actual) else token
                for index, token in enumerate(pointer_tokens(binding.relation.subject_pointer))]
            targets = [value for value in roots if value[1] == pointer_of(target)]
            if len(targets) == 1:
                configured[(root, binding.relation.kind)] = targets[0]
    kept, present = [], set()
    for value in reply.get('relations') or []:
        subject, target = identity(value.get('subject')), identity(value.get('target'))
        if subject not in selectable or target not in selectable:
            continue
        aimed = next((goal for (root, kind), goal in configured.items()
            if identity(selector(root)) == subject and kind == value.get('kind')), None)
        if aimed is not None and identity(selector(aimed)) != target:
            continue
        kept.append(value)
        present.add((subject, value.get('kind')))
    existing = {(value.subject, value.kind): value.ref for value in references.relations} if references else {}
    def refs(root):
        return list(dict.fromkeys(ref for entry in roots[root] for ref in entry.get('evidence') or []))
    derived = []
    for (root, kind), target in sorted(configured.items(), key=lambda pair: (_natural(pair[0][0][1]), pair[0][0][0], pair[0][1])):
        subject = selector(root)
        if subject is None or selector(target) is None or (identity(subject), kind) in present:
            continue
        evidence = refs(root) or refs(target)
        if not evidence:
            continue
        reference = existing.get((subject.get('ref'), kind)) if subject['kind'] == 'handle' else None
        relation = {'kind': 'relation', 'ref': reference} if reference else {
            'kind': 'new', 'key': 'link-' + (subject.get('key') or subject.get('ref')) + '-' + kind}
        derived.append({'relation': relation, 'kind': kind, 'subject': subject, 'target': selector(target), 'evidence': evidence})
        present.add((identity(subject), kind))
    return kept + derived
