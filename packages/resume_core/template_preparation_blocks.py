"""Serialize Python-owned display changes with original guards and retained children."""

from .rich_dependencies import placements
from .templates.compiler import canonical


def changed_block_steps(before, after):
    old = {block.id: block for block in before.blocks()}
    new = {block.id: block for block in after.blocks()}
    old_places, new_places = placements(before), placements(after)
    removed, added = old.keys() - new.keys(), new.keys() - old.keys()
    steps = [{'kind': 'remove_block', 'blockId': identifier, 'beforeRevision': old[identifier].revision}
        for identifier in old if identifier in removed and old_places[identifier][0] not in removed]
    for identifier, block in new.items():
        parent, previous, _owner = new_places[identifier]
        if identifier in added:
            if parent not in added:
                steps.append({'kind': 'put_block', 'parentId': parent, 'afterId': previous,
                    'beforeRevision': None, 'block': block.model_dump(by_alias=True)})
        elif canonical(block.model_dump(exclude={'children', 'revision'})) != canonical(
                old[identifier].model_dump(exclude={'children', 'revision'})):
            value = block.model_dump(by_alias=True)
            value['children'] = []
            steps.append({'kind': 'put_block', 'parentId': parent, 'afterId': previous,
                'beforeRevision': old[identifier].revision, 'block': value, 'keepChildren': True})
    return steps, {identifier: [] for identifier in removed}
