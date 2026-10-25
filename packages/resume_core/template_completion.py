"""Protocol 5: the coordinator completes the bookkeeping a reply's payload implies.

A reply states the payload and the evidence of its values. Which item a value belongs to, the add lineage of new
items and the relations the template configures follow from payload pointers and the compiled bindings, so they
are derived here when the reply leaves them out or names them inconsistently. A value copied word for word from
an offered entry cites the narrowest entries that contain it; a value whose words the source states in another
form or order cites the few narrowest entries that state them all, and the review checks that support. What cannot
be derived stays missing, and the existing checks refuse it with the binding named: a value with no evidence, a
selection the request did not offer, an explicit split or merge that names unknown items.

Repairs (LIVE-05..07) also showed bookkeeping the payload contradicts: an entry for a position the payload no longer
has, or that no binding holds, carries no fact and is dropped; an entry inside a bound value cites that value, and
the raw wording of a date or period cites the values read from it; a foreign field name at a pointer with one bound
field names that field; an item reference of a type no binding at that pointer holds cannot name that value's item,
so the value gets a new item instead.
"""

from copy import deepcopy
import json
import re

from .template_identity import _binding_instances, _bound_root, empty_value, payload_value
from .templates.projection import pointer_tokens

# A derived value cites at most this many offered entries; each states it word for word.
STATED_LIMIT = 3
# A reworded value binds when at most STATED_LIMIT entries state this share of its word stems (I2). Near the item's
# own cited lines the words are far less ambiguous, so the bar is lower there than in the whole source.
STEM_THRESHOLD_NEAR, STEM_THRESHOLD_FAR = 0.5, 0.8
# Lines around an item's own cited lines that may state its reworded values. An item's header is cited first and its
# content follows, so the window reaches a few lines up and further down; the lines above belong to the previous item.
STEM_WINDOW_BEFORE, STEM_WINDOW_AFTER = 2, 12
# A reworded value may gather its stems from this many lines: a merged technology list (LIVE-12) spans employer,
# project and two technology lines.
STEM_LIMIT = 4


def pointer_of(tokens):
    return ''.join('/' + token.replace('~', '~0').replace('/', '~1') for token in tokens)


def _natural(pointer):
    return [(0, int(token), '') if token.isdecimal() else (1, 0, token) for token in pointer_tokens(pointer)]


def _inside(inner, outer):
    same = (inner.source_id, inner.source_revision, inner.unit_id, inner.unit_revision) == (
        outer.source_id, outer.source_revision, outer.unit_id, outer.unit_revision)
    return same and outer.start <= inner.start and inner.end <= outer.end and (inner.start, inner.end) != (outer.start, outer.end)


def _resolves(payload, pointer):
    if not isinstance(pointer, str):
        return True
    try:
        payload_value(payload, pointer)
    except ValueError:
        return False
    return True


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


def _narrowest(hits):
    return [option for option in hits if not any(other is not option and _inside(other.span, option.span) for other in hits)]


def stating(text, table):
    """Refs of the narrowest offered entries that contain the text word for word."""
    pattern = re.compile(r'(?<!\w)' + re.escape(text) + r'(?!\w)')
    narrow = _narrowest([option for option in table.values() if pattern.search(option.text)])
    return [option.ref for option in narrow[:STATED_LIMIT]]


def stating_words(text, table):
    """Refs of at most STATED_LIMIT narrowest entries that together state every word of the text, ignoring case."""
    words = list(dict.fromkeys(word.casefold() for word in re.findall(r'\w+', text)))
    if not words:
        return []
    def holds(option, word):
        return re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', option.text.casefold()) is not None
    options = _narrowest([option for option in table.values() if any(holds(option, word) for word in words)])
    # Greedy cover: one entry stating all words wins; otherwise the entries adding the most missing words.
    chosen, missing = [], set(words)
    while missing and len(chosen) < STATED_LIMIT:
        best = max(options, key=lambda option: sum(holds(option, word) for word in missing), default=None)
        if best is None or not any(holds(best, word) for word in missing):
            return []
        chosen.append(best)
        missing -= {word for word in missing if holds(best, word)}
    return [option.ref for option in chosen] if not missing else []


def _stems(text):
    """Word stems of a text: the first five characters of words of six or more, words of four or five whole, short
    acronyms such as PDF or WCF whole, and other short words (prepositions, 'для', 'код') dropped so they never pull
    in a line of their own."""
    words = [word for word in re.findall(r'\w+', text) if len(word) >= 4 or (len(word) >= 2 and word.isupper())]
    return list(dict.fromkeys(word.casefold()[:5] if len(word) >= 6 else word.casefold() for word in words))


def stating_stems(text, table, anchors=()):
    """Refs of the narrowest entries whose words share stems with the text (LIVE-12: 'Создание и развитие
    микросервисов' states 'Создавал и развивал микросервисы'), when they state enough of its stems. A value of up to
    three stems cites one line, one more line per four further stems, at most STEM_LIMIT.

    anchors are the refs already cited for the same item. With anchors only lines shortly before the first and within
    STEM_WINDOW_AFTER of the last are candidates and STEM_THRESHOLD_NEAR applies: a technology binds to its own project's line, not to a similar line
    of another project, and a claim the item's lines do not state stays unbound. Without anchors the whole table is
    searched at STEM_THRESHOLD_FAR, and the first line chosen opens the window for the rest. Ties go to the line nearest
    the anchors and the lines already chosen, then to the line stating most of the text, then to the line after the
    anchors rather than before them, then to source order."""
    stems = _stems(text)
    if not stems:
        return []
    order = {ref: index for index, ref in enumerate(table)}
    texts = {ref: option.text.casefold() for ref, option in table.items()}
    def holds(ref, stem):
        return re.search(r'(?<!\w)' + re.escape(stem) + r'\w*', texts[ref]) is not None
    anchored = [order[anchor] for anchor in anchors if anchor in order]
    positions = list(anchored)
    threshold = STEM_THRESHOLD_NEAR if anchored else STEM_THRESHOLD_FAR
    def within(option):
        # The words of one value come from one place. Anchors are an item's header and description, so the window
        # reaches a little above them and further below; a chosen content line may have its header well above it.
        if not positions:
            return True
        chosen_positions = positions[len(anchored):]
        low = min([value - STEM_WINDOW_BEFORE for value in anchored] + [value - STEM_WINDOW_AFTER for value in chosen_positions])
        return low <= order[option.ref] <= max(positions) + STEM_WINDOW_AFTER
    def distance(option):
        return min((abs(order[option.ref] - position) for position in positions), default=0)
    candidates = _narrowest([option for ref, option in table.items() if any(holds(ref, stem) for stem in stems)])
    # A short value is one source line; a long merged value may gather its stems from several.
    limit = min(STEM_LIMIT, 1 + len(stems) // 4)
    chosen, missing = [], set(stems)
    while missing and len(chosen) < limit:
        first = min(anchored, default=0)
        best = max((option for option in candidates if within(option)), key=lambda option: (
            sum(holds(option.ref, stem) for stem in missing), -distance(option), sum(holds(option.ref, stem) for stem in stems),
            order[option.ref] >= first, -order[option.ref]), default=None)
        if best is None or not any(holds(best.ref, stem) for stem in missing):
            break
        chosen.append(best)
        positions.append(order[best.ref])
        candidates = [option for option in candidates if option is not best]
        missing -= {stem for stem in missing if holds(best.ref, stem)}
    return [option.ref for option in chosen] if 1 - len(missing) / len(stems) >= threshold else []


def _under(pointer, ancestor):
    tokens, parent = pointer_tokens(pointer), pointer_tokens(ancestor)
    return len(tokens) > len(parent) and tokens[:len(parent)] == parent


def _value_text(payload, pointer):
    text = stated_text(payload, pointer)
    if text is not None:
        return text
    value = payload_value(payload, pointer)
    if isinstance(value, dict):
        return ' '.join(str(part) for part in value.values() if isinstance(part, (str, int, float)) and str(part).strip())
    return json.dumps(value, ensure_ascii=False)


def _shifted(pointer, removed):
    """The pointer after the list element at removed is deleted: None when it was inside it, one index lower when it
    followed it in the same list, else unchanged."""
    if pointer == removed or _under(pointer, removed):
        return None
    tokens, gone = pointer_tokens(pointer), pointer_tokens(removed)
    if len(tokens) >= len(gone) and tokens[:len(gone) - 1] == gone[:-1] and tokens[len(gone) - 1].isdecimal() \
            and int(tokens[len(gone) - 1]) > int(gone[-1]):
        tokens[len(gone) - 1] = str(int(tokens[len(gone) - 1]) - 1)
        return pointer_of(tokens)
    return pointer


def without_unbound(reply, unbound, instances):
    """The reply without the values at the unbound pointers (I4). A list element whose every bound value is unbound
    leaves its list (a task, a technology); any other value becomes null. Entries and discoveries of the removed values
    go with them and the pointers after a removed element move one index down. Returns the reply and the dropped
    values as {pointer, fieldKey, text}."""
    payload = deepcopy(reply.get('payload'))
    targets = {pointer for pointer, _field in unbound}
    removals, nulls = [], []
    for pointer, _field in unbound:
        tokens, chosen = pointer_tokens(pointer), None
        for depth in range(len(tokens), 0, -1):
            candidate = pointer_of(tokens[:depth])
            if not tokens[depth - 1].isdecimal():
                continue
            if all(value in targets for value in instances if value == candidate or _under(value, candidate)):
                chosen = candidate
            else:
                break
        (removals if chosen is not None else nulls).append(chosen or pointer)
    dropped = [{'pointer': pointer, 'fieldKey': field, 'text': _value_text(payload, pointer)} for pointer, field in unbound]
    fields = [dict(entry) for entry in reply.get('fields') or []]
    discoveries = [dict(value) for value in reply.get('discoveries') or []]
    for pointer in nulls:
        tokens = pointer_tokens(pointer)
        parent = payload_value(payload, pointer_of(tokens[:-1]))
        if isinstance(parent, dict):
            parent[tokens[-1]] = None
        fields = [entry for entry in fields if entry.get('pointer') != pointer and not _under(entry.get('pointer') or '', pointer)]
    for removed in sorted(set(removals), key=_natural, reverse=True):
        tokens = pointer_tokens(removed)
        parent = payload_value(payload, pointer_of(tokens[:-1]))
        if isinstance(parent, list) and int(tokens[-1]) < len(parent):
            del parent[int(tokens[-1])]
        for group in (fields, discoveries):
            kept = []
            for value in group:
                moved = _shifted(value.get('pointer') or '', removed)
                if moved is not None:
                    kept.append({**value, 'pointer': moved})
            group[:] = kept
    return {**reply, 'payload': payload, 'fields': fields, 'discoveries': discoveries or reply.get('discoveries')}, dropped


def complete_reply(reply, bindings, table, references, allowed_relations=None, dropped=None):
    """The referenced reply with derived fields entries, item selections, discoveries, add lineage and relations.

    allowed_relations, when given, is the set of (subject type, kind, target type) the template declares; a model
    relation outside it carries no fact (LIVE-11: one job owned by another) and is dropped.

    dropped, when a list, collects the values no entry can cite as {pointer, fieldKey, text}; they leave the payload
    (I4: a repair that still states a value no source line states) and the reduced reply is completed instead. None
    keeps them, so the existing checks refuse the reply with the binding named and the model gets its one repair."""
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
    kinds = {value.ref: value.semantic_type for value in references.items} if references else {}
    moved = []
    for given in reply.get('fields') or []:
        entry = dict(given)
        pointer = entry.get('pointer')
        if not _resolves(payload, pointer):
            continue
        if isinstance(pointer, str) and pointer not in instances:
            # An entry inside one bound value (LIVE-06: /0/period/raw of a bound period) cites that value.
            holders = [candidate for candidate in instances if under(pointer, candidate)]
            parent = pointer_of(pointer_tokens(pointer)[:-1])
            if holders:
                entry['pointer'] = pointer = max(holders, key=len)
                moved.append(entry)
            elif pointer_tokens(pointer)[-1:] == ['raw'] and any(under(candidate, parent) for candidate in instances):
                # The raw wording of a date or period (LIVE-06: /0/period/raw) is the evidence of the values read from it.
                providers[parent] = list(entry.get('evidence') or [])
                continue
        matches = instances.get(pointer, [])
        item = entry.get('item')
        # An unoffered ref stays as given, so restoring the reply still refuses it.
        if (isinstance(item, dict) and item.get('kind') == 'handle' and matches and item.get('ref') in kinds
                and kinds[item.get('ref')] not in {semantic for semantic, _field in matches}):
            entry['item'] = None
        fields = {field for _semantic, field in matches}
        if len(fields) == 1 and entry.get('fieldKey') not in fields:
            # A missing or foreign field name (LIVE-07: the role family's 'family' on a tool) names the one bound field.
            if entry.get('fieldKey') is not None:
                moved.append(entry)
            entry['fieldKey'] = next(iter(fields))
        if not matches and isinstance(pointer, str) and any(under(candidate, pointer) for candidate in instances):
            providers[pointer] = list(entry.get('evidence') or [])
            continue
        if not matches and isinstance(pointer, str):
            # No binding holds this pointer, above or below (LIVE-07: /0/project, a null project): no fact to cite.
            continue
        if entry.get('effectiveCells') is None:
            entry['effectiveCells'] = []
        entries.append(entry)
    # A moved or renamed entry joins the value's own entry, if the reply gave one, instead of duplicating it.
    for entry in moved:
        own = next((other for other in entries if other is not entry and not any(other is value for value in moved)
            and (other.get('pointer'), other.get('fieldKey')) == (entry['pointer'], entry.get('fieldKey'))), None)
        if own is not None:
            own['evidence'] = list(dict.fromkeys([*(own.get('evidence') or []), *(entry.get('evidence') or [])]))
            entries = [value for value in entries if value is not entry]
    roots_of = {}
    for pointer, pairs in instances.items():
        roots_of[pointer] = {pointer_of(_bound_root(pointer, semantic, field, bindings)) for semantic, field in pairs}
    def top_root(pointer):
        # The outermost item a value belongs to: a task of a job is anchored by the whole job's lines, not only its own.
        prefixes = [root for roots in roots_of.values() for root in roots
            if isinstance(pointer, str) and (pointer == root or under(pointer, root))]
        return min(prefixes, key=len) if prefixes else None
    def anchors_for(pointer):
        root = top_root(pointer)
        if root is None:
            return []
        return [ref for entry in entries if top_root(entry.get('pointer')) == root for ref in (entry.get('evidence') or [])]
    def derived_evidence(pointer):
        if empty_value(payload_value(payload, pointer)):
            return []
        ancestors = sorted((value for value in providers if under(pointer, value) and providers[value]), key=len)
        if ancestors:
            return providers[ancestors[-1]]
        text = stated_text(payload, pointer)
        if not text:
            return None
        return stating(text, table) or stating_words(text, table) or stating_stems(text, table, anchors_for(pointer)) or None
    given = {(entry.get('pointer'), entry.get('fieldKey')) for entry in entries}
    unbound = []
    for pointer in sorted(instances, key=_natural):
        for _semantic, field in instances[pointer]:
            if (pointer, field) in given:
                continue
            evidence = derived_evidence(pointer)
            if evidence is not None:
                entries.append({'item': None, 'fieldKey': field, 'pointer': pointer, 'evidence': evidence, 'effectiveCells': []})
            elif dropped is not None:
                unbound.append((pointer, field))
    if unbound:
        reduced, gone = without_unbound(reply, unbound, instances)
        dropped.extend(gone)
        return complete_reply(reduced, bindings, table, references, allowed_relations)
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
        'relations': _relations(reply, entries, roots, keys, handles, instances, bindings, references, allowed_relations)}


def _relations(reply, entries, roots, keys, handles, instances, bindings, references, allowed_relations=None):
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
    captured_relations = {value.ref: value for value in references.relations} if references else {}
    types = {identity(selector(root)): root[0] for root in roots if selector(root) is not None}
    for value in reply.get('relations') or []:
        subject, target = identity(value.get('subject')), identity(value.get('target'))
        if subject not in selectable or target not in selectable:
            continue
        if allowed_relations is not None and (types.get(subject), value.get('kind'), types.get(target)) not in allowed_relations:
            continue
        aimed = next((goal for (root, kind), goal in configured.items()
            if identity(selector(root)) == subject and kind == value.get('kind')), None)
        if aimed is not None and identity(selector(aimed)) != target:
            continue
        chosen = value.get('relation') or {}
        captured = captured_relations.get(chosen.get('ref')) if chosen.get('kind') == 'relation' else None
        if captured is not None and (captured.kind != value.get('kind') or subject != ('handle', captured.subject)):
            # A captured relation keeps its subject and kind (LIVE-11: a repair named one for another subject); a
            # relation of another subject or kind is a new one.
            value = {**value, 'relation': {'kind': 'new', 'key': 'link-' + str(subject[1]) + '-' + str(value.get('kind'))}}
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
