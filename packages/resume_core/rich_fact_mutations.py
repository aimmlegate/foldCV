"""Atomic fact mutations and inverses, without a second history cursor."""

from __future__ import annotations

from dataclasses import dataclass

from .models.rich_facts import RichFact, WorkingFacts, WorkingField, RecordTombstone
from .models.rich_mutations import PutRecord, RemoveRecord


@dataclass(frozen=True)
class FactMutationResult:
    facts: WorkingFacts
    inverse: tuple[PutRecord | RemoveRecord, ...]


def _revise(record: RichFact, previous: RichFact | None, floor: int) -> RichFact:
    result = record.model_copy(deep=True)
    result.revision = floor + 1
    for key in type(result).model_fields:
        value = getattr(result, key)
        old = getattr(previous, key, None) if previous is not None else None
        if isinstance(value, WorkingField):
            same = isinstance(old, WorkingField) and value.model_dump(exclude={"revision"}) == old.model_dump(exclude={"revision"})
            value.revision = old.revision if same else max(getattr(old, "revision", 0), floor) + 1
        elif key == "periods":
            old_periods = {period.id: period for period in old} if isinstance(old, list) else {}
            for period in value:
                old_period = old_periods.get(period.id)
                if old_period is not None and period.evidence != old_period.evidence:
                    raise ValueError("working edit cannot replace original period evidence")
                same_period = old_period is not None and period.model_dump(exclude={"revision"}) == old_period.model_dump(exclude={"revision"})
                period.revision = old_period.revision if same_period else max(getattr(old_period, "revision", 0), floor) + 1
                for part in ("start", "end", "present"):
                    field = getattr(period, part)
                    old_field = getattr(old_period, part, None)
                    same = old_field is not None and field.model_dump(exclude={"revision"}) == old_field.model_dump(exclude={"revision"})
                    field.revision = old_field.revision if same else max(getattr(old_field, "revision", 0), floor) + 1
    return result


def apply_record_mutations(facts: WorkingFacts, steps: list[PutRecord | RemoveRecord], action_id: str) -> FactMutationResult:
    records = {record.id: record for record in facts.records}
    tombstones = {item.record_id: item for item in facts.tombstones}
    order = [record.id for record in facts.records]
    inverse: list[PutRecord | RemoveRecord] = []
    touched: set[str] = set()
    restored_positions: dict[str, int] = {}
    for step in steps:
        record_id = step.record.id if isinstance(step, PutRecord) else step.record_id
        if record_id in touched:
            raise ValueError("duplicate record mutation")
        touched.add(record_id)
        old = records.get(record_id)
        removed = tombstones.get(record_id)
        current_revision = old.revision if old is not None else removed.revision if removed is not None else None
        if step.before_revision != current_revision:
            raise ValueError("stale record mutation")
        if isinstance(step, RemoveRecord):
            if old is None:
                raise ValueError("missing record mutation target")
            del records[record_id]
            tombstones[record_id] = RecordTombstone(recordId=record_id, revision=old.revision + 1,
                                                   actionId=action_id, orderIndex=order.index(record_id))
            inverse.append(PutRecord(kind="put_record", beforeRevision=old.revision + 1, record=old))
        else:
            if old is not None and (step.record.kind != old.kind or step.record.origin != old.origin
                                    or step.record.evidence != old.evidence):
                raise ValueError("working edit cannot replace record identity or original evidence")
            updated = _revise(step.record, old, current_revision or 0)
            records[record_id] = updated
            tombstones.pop(record_id, None)
            if record_id not in order:
                if removed is not None:
                    restored_positions[record_id] = removed.order_index
                else:
                    order.append(record_id)
            inverse.append(PutRecord(kind="put_record", beforeRevision=updated.revision, record=old)
                           if old is not None else RemoveRecord(kind="remove_record", recordId=record_id, beforeRevision=updated.revision))
    order = [record_id for record_id in order if record_id in records]
    for record_id, position in sorted(restored_positions.items(), key=lambda item: (item[1], item[0])):
        order.insert(min(position, len(order)), record_id)
    result = WorkingFacts(revision=facts.revision + (1 if steps else 0),
                          records=[records[record_id] for record_id in order if record_id in records],
                          tombstones=list(tombstones.values()),
                          extraction=facts.extraction.model_copy(deep=True) if facts.extraction else None)
    return FactMutationResult(result, tuple(reversed(inverse)))
