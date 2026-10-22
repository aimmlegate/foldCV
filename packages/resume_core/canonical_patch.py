"""Build and guard leaf patches without retaining unchanged large values."""

from bisect import bisect_left
from collections import Counter
import json
import re

from .models.canonical_patch import CanonicalPatchV1
from .templates.compiler import canonical, sha256


def tokens(pointer):
    if not pointer.startswith('/') or re.search(r'~(?:[^01]|$)', pointer):
        raise ValueError('invalid non-root JSON pointer')
    return [part.replace('~1', '/').replace('~0', '~') for part in pointer[1:].split('/')]


def pointer(parts):
    return '/' + '/'.join(str(part).replace('~', '~0').replace('/', '~1') for part in parts)


def strict_value(wire):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def invalid(_value):
        raise ValueError('nonfinite JSON value')
    value = json.loads(wire, object_pairs_hook=pairs, parse_constant=invalid)
    if canonical(value).decode() != wire:
        raise ValueError('noncanonical JSON value')
    return value


def splice_text(value, start, end, text):
    raw = value.encode('utf-16-le')
    if not 0 <= start <= end <= len(raw) // 2:
        raise ValueError('text splice outside UTF-16 range')
    return raw[:start * 2].decode('utf-16-le') + text.encode('utf-8').decode() + raw[end * 2:].decode('utf-16-le')


class _Node:
    def __init__(self, value):
        self.value = value
        self.children = {key: _Node(child) for key, child in value.items()} if isinstance(value, dict) else (
            [_Node(child) for child in value] if isinstance(value, list) else None)
        self.original = {child: index for index, child in enumerate(self.children)} if isinstance(self.children, list) else {}

    def output(self):
        if isinstance(self.children, dict):
            return {key: child.output() for key, child in self.children.items()}
        if isinstance(self.children, list):
            return [child.output() for child in self.children]
        return self.value


def apply_patch(value, steps):
    steps = CanonicalPatchV1(schemaVersion=1, steps=steps).steps
    root = _Node(value)
    changed, descendants, arrays = set(), set(), {}

    def phase(node, number, index):
        previous = arrays.get(node)
        if previous is not None:
            old_phase, old_index = previous
            if (number < old_phase or number == old_phase and
                    (index < old_index if number == 0 else index >= old_index if number == 1 else index <= old_index)):
                raise ValueError('unordered or repeated array patch target')
        arrays[node] = number, index

    def access(node, key, *, insert=False):
        if isinstance(node.children, dict):
            return key
        if isinstance(node.children, list) and re.fullmatch(r'0|[1-9][0-9]*', key):
            index = int(key)
            if index < len(node.children) + int(insert):
                return index
        raise ValueError('patch parent or index does not exist')

    for step in steps:
        path = tokens(step.pointer)
        node, ancestors = root, []
        for part in path[:-1]:
            if node in changed:
                raise ValueError('patch descends into replaced value')
            ancestors.append(node)
            key = access(node, part)
            child = node.children[key] if isinstance(node.children, list) else node.children.get(key)
            if child is None:
                raise ValueError('patch parent does not exist')
            if child in changed:
                raise ValueError('patch descends into replaced value')
            if isinstance(node.children, list):
                phase(node, 0, node.original[child])
            node = child
        if node in changed:
            raise ValueError('patch descends into replaced value')
        ancestors.append(node)
        key = access(node, path[-1], insert=step.kind == 'insert')
        target = (node.children[key] if key < len(node.children) else None) if isinstance(node.children, list) else node.children.get(key)
        if step.kind == 'insert':
            if not isinstance(node.children, list):
                raise ValueError('insert requires an array')
            phase(node, 2, key)
        else:
            if target is None and step.kind != 'set':
                raise ValueError('patch target does not exist')
            if target is not None and (target in changed or target in descendants):
                raise ValueError('overlapping patch targets')
            if isinstance(node.children, list):
                phase(node, 1 if step.kind == 'remove' else 0, node.original[target])
        if step.kind in {'set', 'insert'}:
            replacement = _Node(strict_value(step.value_wire))
        elif step.kind == 'splice_text':
            if not isinstance(target.value, str) or sha256(target.value.encode()) != step.before_text_hash:
                raise ValueError('text splice hash or type mismatch')
            replacement = _Node(splice_text(target.value, step.start, step.end, step.text))
        if step.kind == 'remove':
            node.children.pop(key)
        elif step.kind == 'insert':
            node.children.insert(key, replacement)
        else:
            node.children[key] = replacement
        if target is not None and step.kind != 'insert':
            changed.add(target)
        if step.kind != 'remove':
            changed.add(replacement)
        descendants.update(ancestors)
    return root.output()


def _identity(value):
    return value.get('id') if isinstance(value, dict) and isinstance(value.get('id'), str) else None


def _array_pairs(before, after):
    size, other = len(before), len(after)
    old_wire, new_wire = [canonical(value) for value in before], [canonical(value) for value in after]
    prefix = 0
    while prefix < min(size, other) and old_wire[prefix] == new_wire[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(size, other) - prefix and old_wire[size - suffix - 1] == new_wire[other - suffix - 1]:
        suffix += 1
    ids_old, ids_new = Counter(_identity(value) for value in before), Counter(_identity(value) for value in after)
    old_counts, new_counts = Counter(old_wire[prefix:size - suffix]), Counter(new_wire[prefix:other - suffix])
    by_id = {_identity(after[j]): j for j in range(prefix, other - suffix)
        if _identity(after[j]) is not None and ids_new[_identity(after[j])] == 1}
    by_wire = {new_wire[j]: j for j in range(prefix, other - suffix) if new_counts[new_wire[j]] == 1}
    candidates = set()
    for index in range(prefix, size - suffix):
        identity = _identity(before[index])
        if identity is not None and ids_old[identity] == 1 and identity in by_id:
            candidates.add((index, by_id[identity]))
        if old_counts[old_wire[index]] == 1 and old_wire[index] in by_wire:
            candidates.add((index, by_wire[old_wire[index]]))
    # Patience matching keeps the smallest new terminal index, then the earlier old index.
    ordered = sorted(candidates)
    tails, tail_nodes, links = [], [], []
    for index, (_old, new) in enumerate(ordered):
        length = bisect_left(tails, new)
        links.append(tail_nodes[length - 1] if length else None)
        if length == len(tails):
            tails.append(new); tail_nodes.append(index)
        elif new < tails[length]:
            tails[length], tail_nodes[length] = new, index
    anchors, cursor = [], tail_nodes[-1] if tail_nodes else None
    while cursor is not None:
        anchors.append(ordered[cursor]); cursor = links[cursor]
    anchors.reverse()
    pairs = [(index, index) for index in range(prefix)]
    old_start = new_start = prefix
    for old_end, new_end in [*anchors, (size - suffix, other - suffix)]:
        if old_end - old_start == new_end - new_start:
            for old, new in zip(range(old_start, old_end), range(new_start, new_end)):
                left, right = _identity(before[old]), _identity(after[new])
                if left is None or right is None or left == right:
                    pairs.append((old, new))
        if old_end < size - suffix:
            pairs.append((old_end, new_end))
        old_start, new_start = old_end + 1, new_end + 1
    pairs.extend((size - suffix + index, other - suffix + index) for index in range(suffix))
    return pairs


def build_patch(before, after):
    steps = []
    def visit(old, new, path):
        if canonical(old) == canonical(new):
            return
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(old.keys() | new.keys()):
                if key not in new:
                    steps.append({'kind': 'remove', 'pointer': pointer([*path, key])})
                elif key not in old:
                    steps.append({'kind': 'set', 'pointer': pointer([*path, key]), 'valueWire': canonical(new[key]).decode()})
                else:
                    visit(old[key], new[key], [*path, key])
        elif isinstance(old, list) and isinstance(new, list):
            pairs = _array_pairs(old, new)
            for left, right in sorted(pairs):
                visit(old[left], new[right], [*path, left])
            retained_old, retained_new = {left for left, _ in pairs}, {right for _, right in pairs}
            for index in reversed(range(len(old))):
                if index not in retained_old:
                    steps.append({'kind': 'remove', 'pointer': pointer([*path, index])})
            for index, value in enumerate(new):
                if index not in retained_new:
                    steps.append({'kind': 'insert', 'pointer': pointer([*path, index]), 'valueWire': canonical(value).decode()})
        elif isinstance(old, str) and isinstance(new, str):
            start = 0
            while start < min(len(old), len(new)) and old[start] == new[start]:
                start += 1
            end = 0
            while end < min(len(old), len(new)) - start and old[-end - 1] == new[-end - 1]:
                end += 1
            stop = len(old) - end
            steps.append({'kind': 'splice_text', 'pointer': pointer(path), 'beforeTextHash': sha256(old.encode()),
                'start': len(old[:start].encode('utf-16-le')) // 2, 'end': len(old[:stop].encode('utf-16-le')) // 2,
                'text': new[start:len(new) - end]})
        else:
            steps.append({'kind': 'set', 'pointer': pointer(path), 'valueWire': canonical(new).decode()})
    visit(before, after, [])
    result = CanonicalPatchV1(schemaVersion=1, steps=steps).steps
    if canonical(apply_patch(before, result)) != canonical(after):
        raise ValueError('patch derivation did not reproduce exact target')
    return result
