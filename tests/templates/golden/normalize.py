"""Normalized result hash of the golden mutation corpus: the oracle for every writer of authored edits.

The hash covers the workspace serialized by `canonical` after dropping revision counters (`syncedFactRevision` is a
span's copy of its record's `revision`), the timestamp and the replay window, and after replacing the ids a step created
with `#1`, `#2`, ... in order of first appearance. Sync rows live beside `project`, so the whole workspace is hashed.
"""

import re

from packages.resume_core.templates.compiler import canonical, sha256


DROPPED = frozenset({'revision', 'projectRevision', 'documentRevision', 'updatedAt', 'mutationReplay', 'syncedFactRevision'})


def _strip(value):
    if isinstance(value, dict):
        return {key: _strip(child) for key, child in value.items() if key not in DROPPED}
    if isinstance(value, list):
        return [_strip(child) for child in value]
    return value


def normalized_text(workspace, created):
    text = canonical(_strip(workspace.model_dump(mode='json', by_alias=True))).decode()
    present = sorted((text.find(identifier), identifier) for identifier in set(created) if identifier and identifier in text)
    if not present:
        return text
    names = {identifier: '#%d' % (index + 1) for index, (_position, identifier) in enumerate(present)}
    pattern = re.compile('|'.join(re.escape(identifier) for identifier in sorted(names, key=len, reverse=True)))
    return pattern.sub(lambda match: names[match.group(0)], text)


def normalized_hash(workspace, created):
    return sha256(normalized_text(workspace, created).encode())


def created_ids(created):
    """Allocated ids of one preparation's `createdIds` ({opId: {slot: id}}), in slot order."""
    return [identifier for slots in created.values() for identifier in slots.values()]


def id_values(workspace):
    """String values under id-like keys (`id`, `*Id`, `*Ids`, `*Handle`, `*Handles`); keys themselves are not ids."""
    found = set()
    def visit(value, identity=False):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, key == 'id' or key.endswith(('Id', 'Ids', 'Handle', 'Handles')))
        elif isinstance(value, list):
            for child in value:
                visit(child, identity)
        elif identity and isinstance(value, str):
            found.add(value)
    visit(workspace.model_dump(mode='json', by_alias=True))
    return found


def new_ids(after, *earlier):
    """Ids in `after` that no earlier state of the same entry held: the ids a step created."""
    seen = set()
    for state in earlier:
        seen |= id_values(state)
    return sorted(id_values(after) - seen)
