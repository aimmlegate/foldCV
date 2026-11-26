"""The undoable values of a V7 project, keyed by kind and id; the undo journal records changes to these keys."""

from .dependencies import placements
from ..template_anchors import coverage_addresses


def values(workspace):
    project = workspace.project
    result = {('block', block.id): block.model_dump(mode='json', by_alias=True, exclude={'children'})
        for block in project.document.blocks()}
    result.update({('placement', key): list(value) for key, value in placements(project.document).items()})
    for name, items in [('builtin', project.facts.records), ('extension', project.facts.extensions),
            ('relation', project.facts.relations), ('issue', project.import_issues)]:
        result.update({(name, item.id): item.model_dump(mode='json', by_alias=True) for item in items})
    result.update({('builtin_scope', key): value for key, value in project.facts.builtin_manual_scopes.items()})
    result.update({('model_written', key): value for key, value in project.facts.model_written.items()})
    result.update({('tombstone', item.record_id): item.model_dump(mode='json', by_alias=True) for item in project.facts.tombstones})
    # D185: the hidden store moves with the blocks it holds, so an Undo of Hide or Show restores both.
    result.update({('hidden', entry.id): entry.model_dump(mode='json', by_alias=True) for entry in project.hidden_blocks})
    result.update({('coverage_anchor', address): item.model_dump(mode='json', by_alias=True)
        for address, item in zip(coverage_addresses(project), project.import_coverage, strict=True)})
    previous = None
    for row in workspace.sync_records:
        result[('sync', row.id)] = row.model_dump(mode='json', by_alias=True)
        result[('sync_placement', row.id)] = {'afterSyncId': previous}
        previous = row.id
    return result
