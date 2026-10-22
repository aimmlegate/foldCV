"""Builtin task/review inputs expose current authority and retained admission only."""

from types import SimpleNamespace
import json

import pytest

from packages.resume_core.models.template_facts import WorkingFactsV2
from packages.resume_core.template_effective import builtin_effective_cells, effective_cells
from packages.resume_core.template_import import dispatch_attempt, record_return, reserve_attempt
from packages.resume_core.template_proposals import parse_proposal
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.templates.models import InputRef
from resume_api.importer.template_pipeline import TemplatePipeline
from tests.templates.employment_fixtures import employment_package, employment_proposal, employment_source
from tests.templates.pipeline_fixtures import NOW, cleaned, owner, usage
from tests.templates.test_builtin_admission import accept, proposed_from, proposal_ready
from tests.templates.test_builtin_scopes import joined_edit, scoped_workspace
from packages.resume_core.rich_mutations import apply_rich_mutation


def admitted_employment(*, invalid_metric=False):
    package = employment_package()
    src, _ = employment_source('F01')
    reply = employment_proposal(src, unsupported=invalid_metric)
    operation, facts, proposed, _package, _src = proposed_from(package, src, reply)
    rejected = [allocation.cell_ids['value'] for allocation in operation.allocations
        if allocation.key == 'results-entry'] if invalid_metric else []
    operation, facts = accept(operation, facts, proposed, package, src, rejected)
    return operation, facts, package, src


def test_builtin_cells_reuse_exact_canonical_ids_dates_and_real_receipts_without_storage_copies():
    operation, facts, _package, _src = admitted_employment()
    before = canonical(facts)
    projected = builtin_effective_cells(facts, [operation])
    ids = {cell.id for cell in projected}
    assert set(operation.proposals[0].admitted_cell_ids) - {cell.id for record in facts.extensions for cell in record.cells} == ids
    assert all(cell.origin == 'source' and cell.state == 'admitted' for cell in projected)
    assert all(cell.admission_receipt_ids == [operation.proposals[0].applied_receipt_id] for cell in projected)
    start = next(cell for cell in projected if cell.field_key.endswith(':start'))
    assert start.typed_value == {'precision': 'month', 'year': 2020, 'month': 3, 'day': None}
    assert start.raw_input == '03.2020'
    assert canonical(facts) == before
    assert not any(cell.id in ids for record in facts.extensions for cell in record.cells)


@pytest.mark.parametrize('corruption', ['no_operation', 'no_admission', 'changed_observation', 'changed_field', 'record_flag'])
def test_unretained_or_stale_typed_values_do_not_acquire_effective_authority(corruption):
    operation, facts, _package, _src = admitted_employment()
    job = next(record for record in facts.records if record.kind == 'employment')
    allocation = next(value for value in operation.allocations if value.record_id == job.id)
    target = allocation.cell_ids['company']
    operations = [operation]
    if corruption == 'no_operation':
        operations = []
    elif corruption == 'no_admission':
        operation.proposals[0].admitted_cell_ids.remove(target)
    elif corruption == 'changed_observation':
        next(value for value in facts.observations if value.item_handle == allocation.item_handle
            and value.field_key == 'company').typed_value = 'Unreviewed employer'
        job.employer.value = job.employer.raw_text = 'Unreviewed employer'
    else:
        job.employer.value = job.employer.raw_text = 'Unreviewed employer'
        job.user_corrected = corruption == 'record_flag'
    assert target not in {cell.id for cell in builtin_effective_cells(facts, operations)}


def test_shared_pending_and_legacy_pending_inputs_never_expose_obsolete_typed_values():
    before, _sources = scoped_workspace()
    command, scope = joined_edit(before)
    changed, _ = apply_rich_mutation(before, command)
    cells = {cell.id: cell for cell in builtin_effective_cells(changed.project.facts, [])}
    for identifier in scope['cellIds']:
        assert cells[identifier].typed_value is None and cells[identifier].raw_input == ''
        assert cells[identifier].state == 'pending_manual' and cells[identifier].manual_scope_id == scope['id']
    legacy = next(record for record in before.project.facts.records if record.id == 'employer-b')
    legacy.role.status, legacy.role.pending_raw_text, legacy.role.user_corrected = 'pending', 'Exact pending role', True
    cell = next(cell for cell in builtin_effective_cells(before.project.facts, []) if cell.field_key == 'role'
        and 'employer-b' in cell.id)
    assert cell.typed_value is None and cell.raw_input == 'Exact pending role' and cell.state == 'human_raw'


def test_task_input_contains_builtin_cells_and_scopes_without_unreviewed_record_fields():
    operation, facts, package, src = admitted_employment(invalid_metric=True)
    definition = package.definition.model_copy(deep=True)
    definition.blocks[0].selectors += [InputRef(kind='fact_type', id='employment'), InputRef(kind='fact_type', id='claim')]
    # The input projection reads only the captured declaration; compilation is tested separately.
    package = package.model_copy(update={'definition': definition})
    job = next(record for record in facts.records if record.kind == 'employment')
    allocation = next(value for value in operation.allocations if value.record_id == job.id)
    scope = {'id': 'human-scope', 'actionId': 'edit', 'rawInput': 'Exact joined edit',
        'cellIds': [allocation.cell_ids['company']], 'blockIds': []}
    data = facts.model_dump(by_alias=True)
    data['manualScopes'] = [scope]
    data['builtinManualScopes'] = {allocation.cell_ids['company']: scope['id']}
    employer = next(record for record in data['records'] if record['id'] == job.id)['employer']
    employer.update(value=None, status='pending', pendingRawText=scope['rawInput'], userCorrected=True)
    facts = WorkingFactsV2.model_validate(data)
    owner_data = SimpleNamespace(facts=facts, template_package=package, sources=[src], template_operations=[operation])
    value, handles = TemplatePipeline.task_input(None, operation, operation.tasks[0], owner_data)
    assert allocation.item_handle in handles
    assert value['manualScopes'] == [scope]
    projected_job = next(record for record in value['effectiveRecords'] if record['id'] == job.id)
    assert projected_job['builtinKind'] == 'employment' and 'employer' not in projected_job
    cell = next(cell for cell in projected_job['cells'] if cell['id'] == allocation.cell_ids['company'])
    assert cell['typedValue'] is None and cell['manualScopeId'] == scope['id']
    assert all('80%' not in str(cell['typedValue']) for cell in value['effectiveCells'])
    assert not any(record.get('builtinKind') == 'claim' and any('80%' in str(cell['typedValue'])
        for cell in record['cells']) for record in value['effectiveRecords'])


def test_rejected_allocated_builtin_cell_cannot_be_cited_as_effective_evidence(tmp_path):
    operation, facts, proposed, package, src = proposal_ready(tmp_path)
    job = next(value for value in operation.allocations if value.key == 'job-a')
    rejected = job.cell_ids['start']
    operation, facts = accept(operation, facts, proposed, package, src, [rejected])
    assert rejected not in {cell.id for cell in effective_cells(facts, [operation])}
    reply = proposed.reply.model_dump(mode='json', by_alias=True)
    reply['fields'][0]['effectiveCellIds'] = [rejected]
    operation, attempt = reserve_attempt(operation, operation.tasks[0].id, 'primary_repair', operation.tasks[0].input_hash,
        operation.capture.primary, owner(3), NOW)
    operation = dispatch_attempt(operation, attempt, NOW)
    operation = record_return(operation, attempt, json.dumps({'payload': reply}), 'completed', usage(), cleaned(), returned_at=NOW)
    _operation, _facts, rejected_proposal = parse_proposal(operation, attempt, package, [src], facts)
    assert rejected_proposal.state == 'invalid'
    assert 'unknown/unadmitted effective cell' in rejected_proposal.errors
