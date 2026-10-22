"""Scoped dependency stamps shared by previews, delayed replies and cascades."""

import hashlib
import json

from .models.rich_mutations import DependencyStamp
from .rich_fields import records_by_id, working_field


def fingerprint(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def placements(document):
    result = {}
    def visit(items, parent, owner):
        previous = None
        for block in items:
            record = getattr(block.props, "record_id", None)
            result[block.id] = (parent, previous, record or owner)
            visit(block.children, block.id, record or owner)
            previous = block.id
    for region in document.regions:
        visit(region.blocks, region.id, None)
    return result


def dependency(workspace, kind, identifier):
    project = workspace.project
    if project is None:
        raise ValueError("DEPENDENCY_MISSING")
    blocks = {block.id: block for block in project.document.blocks()}
    records = records_by_id(project.facts)
    target = None
    if kind in {"block", "record"}:
        target = (blocks if kind == "block" else records).get(identifier)
    elif kind == "field":
        try:
            namespace, owner, key = json.loads(identifier)
            if namespace == "fact" and owner in records:
                target = working_field(records[owner], key)
            elif namespace == "cell" and owner in blocks:
                block = blocks[owner]
                target = next((cell for row in block.content.rows for cell in row.cells if cell.id == key), None)
            elif namespace == 'template':
                from .template_dependencies import target as template_target
                target = template_target(workspace, owner, key)
        except (ValueError, TypeError, AttributeError):
            pass
    elif kind == "period":
        target = next((period for record in records.values() for period in getattr(record, "periods", []) if period.id == identifier), None)
    elif kind == "ownership":
        placement = placements(project.document).get(identifier)
        if placement is not None:
            # Parent identity, rather than global document revision, guards scoped moves.
            return DependencyStamp(kind=kind, id=identifier, revision=1, fingerprint=fingerprint(placement))
    elif kind == "source":
        target = next((source for source in project.sources if source.id == identifier), None)
    elif kind == "rules" and workspace.rules_used is not None:
        target = workspace.rules_used
    elif kind == "asset":
        target = next((asset for asset in project.assets if asset.id == identifier), None)
    elif kind == "timeline_order":
        order = [period.id for record in project.facts.records if record.kind == "employment" for period in record.periods]
        return DependencyStamp(kind=kind, id=identifier, revision=1, fingerprint=fingerprint(order))
    if target is None:
        raise ValueError("DEPENDENCY_MISSING")
    return DependencyStamp(kind=kind, id=identifier, revision=getattr(target, "revision", 1), fingerprint=fingerprint(target))


def dependencies_current(workspace, stamps):
    try:
        for stamp in stamps:
            current = dependency(workspace, stamp.kind, stamp.id)
            if current.revision != stamp.revision or (stamp.fingerprint is not None and current.fingerprint != stamp.fingerprint):
                return False
        return True
    except ValueError:
        return False
