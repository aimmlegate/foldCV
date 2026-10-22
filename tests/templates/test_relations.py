"""Relation edits change working ownership and retain original observations."""

from packages.resume_core.models.rich_facts import ClaimRecord, EmploymentRecord
from packages.resume_core.models.template_facts import Relation, WorkingFactsV2
from packages.resume_core.template_facts import delete_subject, move_owned
from tests.templates.storage_fixtures import papers


def text(value):
    return {'value': value, 'rawText': value, 'status': 'known', 'revision': 1, 'pendingRawText': None}


def facts():
    value = papers()
    value.records = [EmploymentRecord(id=identifier, revision=1, origin='user', evidence=[],
        kind='employment', employer=text(identifier), role=text('Engineer'), periods=[])
        for identifier in ['employer-a', 'employer-b']]
    value.records.append(ClaimRecord(id='claim', revision=1, origin='user', evidence=[], kind='claim',
        jobId='employer-a', subprojectId=None, value=text('Maintained a queue')))
    reference = value.extensions[1].model_copy(deep=True)
    reference.id = 'reference'
    reference.item_handle = 'reference-handle'
    for cell in reference.cells:
        cell.id = 'reference-' + cell.field_key
    value.extensions.append(reference)
    for identifier, kind, subject in [('award-owner', 'owned_by', 'paper-a'),
                                      ('division-subject', 'extension_of', 'paper-b'),
                                      ('reference-target', 'related_to', 'reference')]:
        relation = Relation(id=identifier, kind=kind, subjectId=subject, targetId='employer-a', revision=1, active=True)
        value.relations.append(relation)
        next(record for record in value.extensions if record.id == subject).relations.append(relation)
    return WorkingFactsV2.model_validate(value.model_dump(by_alias=True))


def test_moves_follow_relation_kind_without_replacing_original_ownership():
    original = facts()
    changed = move_owned(original, 'claim', 'employer-b', supported_owner_ids=['employer-a', 'employer-b'])
    changed = move_owned(changed, 'paper-a', 'employer-b', supported_owner_ids=['employer-a', 'employer-b'])
    fixed_subject = move_owned(changed, 'paper-b', 'employer-b', supported_owner_ids=['employer-a', 'employer-b'])
    assert next(r for r in fixed_subject.records if r.id == 'claim').job_id == 'employer-b'
    assert fixed_subject.extensions[0].relations[0].target_id == 'employer-b'
    assert fixed_subject.extensions[1].relations[0].target_id == 'employer-a'
    assert original.extensions[0].relations[0].target_id == 'employer-a'
    assert fixed_subject.extensions[2] == original.extensions[2]


def test_explicit_owner_deletion_tombstones_owned_and_attached_but_retains_referrer():
    original = facts()
    deleted = delete_subject(original, 'employer-a', 'delete-action')
    assert {t.record_id for t in deleted.tombstones} == {'employer-a', 'claim', 'paper-a', 'paper-b'}
    assert [r.id for r in deleted.records] == ['employer-b']
    assert [r.id for r in deleted.extensions if r.active] == ['reference']
    assert all(not r.active for r in deleted.relations)
    assert deleted.observations == original.observations
