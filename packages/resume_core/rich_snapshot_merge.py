"""Merge declared metadata against its acknowledged base, never a stale resume."""

from copy import deepcopy

from pydantic import BaseModel

from .background_store import BackgroundFailure

COLLECTIONS = frozenset({"operations", "sources", "assets", "syncRecords", "warnings", "renders"})
ATOMIC = frozenset({"document", "facts", "evidenceRecords", "template", "rulesUsed", "mutationReplay", "metadata_record", "importDraft"})


def item_key(item, field):
    return (item["id"], item["revision"]) if field == "sources" else item["id"]


def merge_value(base, proposed, current, field=""):
    if proposed == base:
        return deepcopy(current)
    if current == base or current == proposed:
        return deepcopy(proposed)
    if field == "updatedAt":
        from datetime import datetime
        return max((proposed, current), key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
    if field in ATOMIC:
        raise BackgroundFailure("DEPENDENCY_CHANGED")
    if isinstance(base, dict) and isinstance(proposed, dict) and isinstance(current, dict):
        if base.keys() != proposed.keys() or base.keys() != current.keys():
            raise BackgroundFailure("DEPENDENCY_CHANGED")
        return {key: merge_value(base[key], proposed[key], current[key], key) for key in base}
    if field in COLLECTIONS and all(isinstance(value, list) for value in (base, proposed, current)):
        # Source revisions are distinct records; identity alone must not collapse them.
        if not all(isinstance(item, dict) and "id" in item for value in (base, proposed, current) for item in value):
            raise BackgroundFailure("DEPENDENCY_CHANGED")
        maps = [{item_key(item, field): item for item in value} for value in (base, proposed, current)]
        if any(len(mapping) != len(value) for mapping, value in zip(maps, (base, proposed, current))):
            raise BackgroundFailure("DEPENDENCY_CHANGED")
        old, changes, latest = maps
        result = []
        for key, item in latest.items():
            if key not in old:
                if key in changes and changes[key] != item:
                    raise BackgroundFailure("DEPENDENCY_CHANGED")
                result.append(deepcopy(item))
            elif key not in changes:
                if item != old[key]:
                    raise BackgroundFailure("DEPENDENCY_CHANGED")
            else:
                result.append(merge_value(old[key], changes[key], item, "metadata_record"))
        for key, item in changes.items():
            if key not in latest:
                if key in old:
                    if item != old[key]:
                        raise BackgroundFailure("DEPENDENCY_CHANGED")
                else:
                    result.append(deepcopy(item))
        old_order = [item_key(item, field) for item in base]
        changed_order = [item_key(item, field) for item in proposed if item_key(item, field) in old]
        if changed_order != [key for key in old_order if key in changes]:
            raise BackgroundFailure("DEPENDENCY_CHANGED")
        return result
    raise BackgroundFailure("DEPENDENCY_CHANGED")


def merge_snapshot(base, proposed, current):
    before, after, latest = [value.model_dump(mode="json", by_alias=True) for value in (base, proposed, current)]
    for key in ("schemaVersion", "projectId", "createdAt"):
        if after[key] != before[key] or latest[key] != before[key]:
            raise BackgroundFailure("JOB_SCOPE_INVALID")
    if after["projectRevision"] < before["projectRevision"] or after["documentRevision"] < before["documentRevision"]:
        raise BackgroundFailure("DEPENDENCY_CHANGED")
    # Assembly changes owners. Only operation metadata may advance in the old owner.
    if before["project"] is None and after["project"] is not None:
        if latest["project"] is not None:
            raise BackgroundFailure("DEPENDENCY_CHANGED")
        old, new = deepcopy(before["preDraft"]), deepcopy(latest["preDraft"])
        old.pop("operations"); new.pop("operations")
        if old != new:
            raise BackgroundFailure("DEPENDENCY_CHANGED")
        after["project"]["operations"] = merge_value(before["preDraft"]["operations"],
            after["project"]["operations"], latest["preDraft"]["operations"], "operations")
        latest["preDraft"] = deepcopy(before["preDraft"])
    for value in (before, after, latest):
        value.pop("projectRevision"); value.pop("documentRevision")
        if value["project"]:
            value["project"].pop("revision")
    result = merge_value(before, after, latest)
    result["projectRevision"] = current.project_revision + proposed.project_revision - base.project_revision
    result["documentRevision"] = result["project"]["document"]["revision"] if result["project"] else current.document_revision
    if result["project"]:
        result["project"]["revision"] = result["projectRevision"]
    return type(proposed).model_validate(result)


def reconcile(target, source):
    """Keep callback references alive when another writer publishes into the cache."""
    if isinstance(target, BaseModel) and type(target) is type(source):
        if type(source).model_config.get("frozen") or any(field.frozen for field in type(source).model_fields.values()):
            return deepcopy(source)
        for key in type(source).model_fields:
            setattr(target, key, reconcile(getattr(target, key), getattr(source, key)))
        return target
    if isinstance(target, list) and isinstance(source, list):
        def key(value):
            return (type(value), getattr(value, "kind", None), getattr(value, "id", None), getattr(value, "revision", None)
                if type(value).__name__ == "Source" else None)
        owned = {key(value): value for value in target if isinstance(value, BaseModel) and hasattr(value, "id")}
        target[:] = [reconcile(owned[key(value)], value) if key(value) in owned else deepcopy(value) for value in source]
        return target
    return deepcopy(source)
