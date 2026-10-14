from pathlib import Path

import pytest

from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.models.rich_mutations import PutRecord, RemoveRecord
from packages.resume_core.rich_fact_mutations import apply_record_mutations


def facts():
    workspace = WorkspaceV6.model_validate_json((Path(__file__).parents[1] / "fixtures/rich_workspace.json").read_text())
    assert workspace.project is not None
    return workspace.project.facts


def test_rich_fact_inverse_restores_values_with_monotonic_revisions():
    initial = facts()
    candidate = initial.records[0]
    edited = candidate.model_copy(deep=True)
    edited.name.value = edited.name.raw_text = "Sam Example"
    result = apply_record_mutations(initial, [PutRecord(kind="put_record", beforeRevision=1, record=edited)], "panel-1")
    assert result.facts.records[0].name.value == "Sam Example"
    assert result.facts.records[0].name.revision == 2
    assert result.facts.records[0].location.revision == 1
    undo = apply_record_mutations(result.facts, list(result.inverse), "undo-1")
    assert undo.facts.records[0].name.value == "Alex Example"
    assert undo.facts.records[0].name.revision == 3
    redo = apply_record_mutations(undo.facts, list(undo.inverse), "redo-1")
    assert redo.facts.records[0].name.value == "Sam Example"
    assert redo.facts.records[0].name.revision == 4
    assert initial.records[0].revision == 1


def test_rich_record_deletion_retains_evidence_and_blocks_old_reply_after_restore():
    initial = facts()
    removed = apply_record_mutations(initial, [RemoveRecord(kind="remove_record", recordId="candidate-1", beforeRevision=1)], "delete-1")
    assert removed.facts.tombstones[0].revision == 2
    with pytest.raises(ValueError, match="stale"):
        apply_record_mutations(removed.facts, [PutRecord(kind="put_record", beforeRevision=1, record=initial.records[0])], "late-1")
    restored = apply_record_mutations(removed.facts, list(removed.inverse), "undo-1")
    assert restored.facts.records[0].revision == 3
    assert restored.facts.records[0].name.revision == 3
    assert not restored.facts.tombstones
    with pytest.raises(ValueError, match="stale"):
        apply_record_mutations(restored.facts, [PutRecord(kind="put_record", beforeRevision=1, record=initial.records[0])], "late-2")


def test_rich_fact_composite_failure_is_atomic_and_cannot_change_evidence():
    initial = facts()
    edited = initial.records[0].model_copy(deep=True)
    edited.name.value = "Sam"
    with pytest.raises(ValueError, match="stale"):
        apply_record_mutations(initial, [PutRecord(kind="put_record", beforeRevision=1, record=edited),
                                        RemoveRecord(kind="remove_record", recordId="job-1", beforeRevision=999)], "bad-1")
    assert initial.records[0].name.value == "Alex Example"
    edited.origin = "source"
    with pytest.raises(ValueError, match="original evidence"):
        apply_record_mutations(initial, [PutRecord(kind="put_record", beforeRevision=1, record=edited)], "bad-2")


def test_rich_employer_edit_keeps_unrelated_period_dependency_current():
    initial = facts()
    job = initial.records[1].model_copy(deep=True)
    job.employer.value = "Renamed employer"
    result = apply_record_mutations(initial, [PutRecord(kind="put_record", beforeRevision=1, record=job)], "panel-1")
    updated = result.facts.records[1]
    assert updated.employer.revision == 2
    assert updated.periods[0].revision == 1
    assert updated.periods[0].start.revision == 1


def test_rich_composite_delete_inverse_restores_record_order():
    initial = facts()
    removed = apply_record_mutations(initial, [
        RemoveRecord(kind="remove_record", recordId="candidate-1", beforeRevision=1),
        RemoveRecord(kind="remove_record", recordId="job-1", beforeRevision=1),
    ], "delete-two")
    restored = apply_record_mutations(removed.facts, list(removed.inverse), "undo-two")
    assert [record.id for record in restored.facts.records] == [record.id for record in initial.records]


def test_source_period_evidence_cannot_be_replaced_by_a_working_edit():
    initial = facts()
    job = initial.records[1].model_copy(deep=True)
    old = job.periods[0].evidence[:]
    from packages.resume_core.models.recovery import EvidenceSpan
    job.periods[0].evidence = [] if old else [EvidenceSpan(sourceId="fabricated", sourceRevision=1, unitId="fabricated", unitRevision=1, text="fabricated")]
    from packages.resume_core.models.rich_facts import EmploymentRecord
    edited = EmploymentRecord.model_validate(job.model_dump(by_alias=True))
    with pytest.raises(ValueError, match="original period evidence"):
        apply_record_mutations(initial, [PutRecord(kind="put_record", beforeRevision=1, record=edited)], "bad-evidence")
    assert initial.records[1].periods[0].evidence == old
