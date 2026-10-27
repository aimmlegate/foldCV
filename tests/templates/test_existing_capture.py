"""Existing identities are captured independently of discovery and effective proof."""

from itertools import count
from types import SimpleNamespace
import pytest

from packages.resume_core.models.template_import import ImportOperation
from packages.resume_core.models.rich_facts import WorkingPeriod
from packages.resume_core.template_capture import capture_existing_items, item_identities, prepare_builtin_identities
from packages.resume_core.template_import import (TemplateImportFailure, admit_operation, digest,
    resume_operation, start_operation)
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.templates.models import InputRef
from resume_api.importer.template_pipeline import TemplatePipeline
from tests.templates.human_authority_fixtures import human_papers
from tests.templates.pipeline_fixtures import NOW, resume_command, setup_operation
from tests.templates.test_builtin_effective import admitted_employment
from tests.templates.test_relations import facts as related_facts
from tests.templates.employment_fixtures import employment_package, employment_source
from packages.resume_core.template_builtin_admission import unknown


def serial():
    index = count()
    return lambda prefix: prefix + '-capture-' + str(next(index))


def test_human_extensions_capture_their_actual_identity_without_any_historical_discovery():
    _empty, command, captured, src, _facts = setup_operation()
    facts = human_papers('pending_manual')
    before = canonical(facts)
    command.capture.fact_revisions = {record.id: record.revision for record in facts.extensions}
    operation, created = start_operation('capture-project', command, captured, [src], facts, [], NOW)
    assert created and not operation.allocations and len(operation.captured_items) == 2
    assert not operation.attempts and not operation.receipts
    for record, identity in zip(facts.extensions, operation.captured_items, strict=True):
        assert (identity.item_handle, identity.record_id, identity.record_revision) == (record.item_handle, record.id, record.revision)
        assert identity.cell_ids == {cell.field_key: cell.id for cell in record.cells}
        assert 'discoveryAttemptId' not in identity.model_dump(by_alias=True)
    assert canonical(facts) == before
    operation = admit_operation(operation, NOW)
    retained = digest(operation.captured_items)
    resumed = resume_operation(operation, resume_command(operation), NOW)
    assert digest(resumed.captured_items) == retained


def test_builtin_admission_retains_mapping_and_future_capture_keeps_exact_period_ids():
    old, facts, captured, src = admitted_employment()
    assert len(facts.builtin_identities) == len(facts.records)
    original = canonical(facts)
    prepared = prepare_builtin_identities(facts, captured, [old], id_factory=serial())
    assert canonical(prepared) == original
    _empty, command, _package, _source, _facts = setup_operation(captured=captured, src=src)
    command.capture.fact_revisions = {record.id: record.revision for record in [*facts.records, *facts.extensions]}
    operation, _created = start_operation('capture-project', command, captured, [src], facts, [], NOW)
    assert not operation.allocations
    for value in facts.builtin_identities:
        identity = next(item for item in operation.captured_items if item.record_id == value.record_id)
        assert identity.period_ids == value.period_ids and identity.canonical_fields == value.canonical_fields
        assert identity.cell_ids == value.cell_ids and identity.item_handle == value.item_handle
    assert {value.record_id for value in item_identities(operation)} == {record.id for record in [*facts.records, *facts.extensions]}


def test_historical_builtin_mapping_is_reused_without_reconstructing_period_order():
    old, facts, captured, _src = admitted_employment()
    retained = facts.builtin_identities[0].model_copy(deep=True)
    facts.builtin_identities = []
    prepared = prepare_builtin_identities(facts, captured, [old], id_factory=lambda _prefix: pytest.fail('must reuse original identity'))
    assert next(value for value in prepared.builtin_identities if value.record_id == retained.record_id) == retained
    assert not facts.builtin_identities


def test_unmapped_existing_periods_fail_preparation_without_changes_or_position_guessing():
    captured = employment_package()
    facts = related_facts()
    facts.records = [record for record in facts.records if record.kind == 'employment']
    facts.extensions, facts.relations, facts.observations = [], [], []
    facts.records[0].periods = [WorkingPeriod(id='human-period', revision=1, start=unknown(), end=unknown(),
        present=unknown(), evidence=[])]
    before = canonical(facts)
    with pytest.raises(ValueError, match='explicit existing period slots'):
        prepare_builtin_identities(facts, captured, [], id_factory=serial())
    assert canonical(facts) == before
    src, _raw = employment_source()
    _operation, command, _package, _source, _facts = setup_operation(captured=captured, src=src)
    command.capture.fact_revisions = {record.id: record.revision for record in facts.records}
    with pytest.raises(TemplateImportFailure, match='IMPORT_IDENTITY_PREPARATION_REQUIRED'):
        start_operation('capture-project', command, captured, [src], facts, [], NOW)


def test_unmapped_human_builtin_without_periods_gets_an_application_identity_not_a_discovery():
    captured = employment_package()
    facts = related_facts()
    facts.records = [record for record in facts.records if record.kind == 'employment']
    facts.extensions, facts.relations, facts.observations = [], [], []
    before = canonical(facts)
    prepared = prepare_builtin_identities(facts, captured, [], id_factory=serial())
    assert canonical(facts) == before and prepared.revision == facts.revision + 1
    assert len(prepared.builtin_identities) == 2
    identities = capture_existing_items(prepared, captured)
    assert [value.record_id for value in identities] == ['employer-a', 'employer-b']
    assert all(value.period_ids and value.record_revision == 1 for value in identities)
    assert all(not record.periods for record in prepared.records)
    assert not prepared.observations


def test_identity_collision_between_capture_and_new_discovery_is_rejected():
    operation, _facts, _captured, _src = admitted_employment()
    allocation = operation.allocations[0]
    from packages.resume_core.models.template_facts import CapturedItemIdentity
    identity = CapturedItemIdentity(**allocation.model_dump(by_alias=True, include={
        'item_handle', 'record_id', 'semantic_type', 'cell_ids', 'period_ids', 'canonical_fields'}),
        recordRevision=1, semanticSchemaHash=digest('synthetic-schema'))
    value = operation.model_dump(by_alias=True)
    value['capture']['factRevisions'][identity.record_id] = 1
    value['capturedItems'] = [identity.model_dump(by_alias=True)]
    with pytest.raises(ValueError, match='identities collide'):
        ImportOperation.model_validate(value)


def test_selected_unproven_builtin_stays_explicit_with_empty_effective_cells():
    captured = employment_package()
    captured.definition.blocks[0].selectors.append(InputRef(kind='fact_type', id='employment'))
    facts = related_facts()
    facts.records = [record for record in facts.records if record.kind == 'employment']
    facts.extensions, facts.relations, facts.observations = [], [], []
    for record in facts.records:
        record.origin = 'source'
    facts = prepare_builtin_identities(facts, captured, [], id_factory=serial())
    src, _raw = employment_source()
    _operation, command, _package, _source, _facts = setup_operation(captured=captured, src=src)
    command.capture.fact_revisions = {record.id: record.revision for record in facts.records}
    operation, _created = start_operation('capture-project', command, captured, [src], facts, [], NOW)
    data = SimpleNamespace(facts=facts, template_package=captured, sources=[src], template_operations=[operation])
    value, handles = TemplatePipeline.task_input(None, operation, operation.tasks[0], data)
    assert set(handles) == {identity.item_handle for identity in operation.captured_items}
    assert not value['effectiveCells']
    assert len(value['effectiveRecords']) == 2
    assert all(record['cells'] == [] and 'employer' not in record for record in value['effectiveRecords'])


def test_save_cannot_refresh_or_erase_an_existing_identity_capture():
    from packages.resume_core.project_store import ProjectStoreFailure
    from packages.resume_core.template_import import retain_operation
    _empty, command, captured, src, _facts = setup_operation()
    facts = human_papers('human_raw')
    command.capture.fact_revisions = {record.id: record.revision for record in facts.extensions}
    operation, _created = start_operation('capture-project', command, captured, [src], facts, [], NOW)
    changed = operation.model_copy(deep=True)
    changed.captured_items.reverse()
    with pytest.raises(ProjectStoreFailure):
        retain_operation(operation, changed)


def test_capture_preserves_reserved_absent_extension_cells_from_real_discovery_history():
    old, facts, package, _src = admitted_employment()
    extension = next(record for record in facts.extensions if not any(cell.field_key == 'attribution' for cell in record.cells))
    allocation = next(value for value in old.allocations if value.record_id == extension.id)
    assert 'attribution' in allocation.cell_ids
    captured = capture_existing_items(facts, package, [old])
    identity = next(value for value in captured if value.record_id == extension.id)
    assert identity.cell_ids == allocation.cell_ids
    assert all(cell.id != identity.cell_ids['attribution'] for cell in extension.cells)


def test_existing_mapping_cannot_silently_omit_a_new_unmapped_period():
    old, facts, package, _src = admitted_employment()
    job = next(record for record in facts.records if record.kind == 'employment')
    job.periods.append(WorkingPeriod(id='unmapped-human-period', revision=1, start=unknown(), end=unknown(),
        present=unknown(), evidence=[]))
    before = canonical(facts)
    with pytest.raises(ValueError, match='explicit existing period slots'):
        prepare_builtin_identities(facts, package, [old], id_factory=serial())
    with pytest.raises(ValueError, match='explicit existing period slots'):
        capture_existing_items(facts, package, [old])
    assert canonical(facts) == before
