"""Prepared deltas preserve exact output without carrying the unchanged resume."""

from dataclasses import replace

import pytest

from packages.resume_core import template_delta
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.canonical_patch import apply_patch
from packages.resume_core.models.template_delta import TemplatePreparedEditDeltaV1
from packages.resume_core.rich_api import RichGenerationState
from packages.resume_core.template_delta import prepare_text_delta, prepared_delta
from packages.resume_core.template_preparation import prepare_text_edit
from packages.resume_core.templates.compiler import canonical, sha256
from tests.templates.test_bounded_history import large_workspace
from tests.templates.test_template_preparation import command, proof, response
from tests.templates.storage_fixtures import workspace


def test_one_character_delta_has_exact_result_and_omits_large_unchanged_resume():
    before, _ = large_workspace()
    base = response(before)
    request = command(before, start=2, end=2, text='!', target={'kind': 'literal'})
    full = prepare_text_edit(base, request, proof())
    delta = prepared_delta(base, full)
    raw = canonical(delta)
    assert len(raw) < 6000
    assert all(value not in raw for value in [b'large-witness', b'Unrelated text', b'"templatePackage"', b'"regions"'])
    restored = apply_patch(before.model_dump(mode='json', by_alias=True), delta.workspace_patch)
    assert canonical(restored) == canonical(full.preview.workspace)
    assert delta.base_workspace_sha256 == sha256(canonical(before))
    assert delta.result_workspace_sha256 == sha256(canonical(restored))
    assert delta.result_snapshot == full.preview.snapshot and delta.result_identity == full.preview.identity
    assert delta.mutation_wire == full.mutation.model_dump_json(by_alias=True)
    assert delta.presentation_patch.set == {} and delta.presentation_patch.remove == []
    assert delta.created_ids == full.created_ids
    assert canonical(prepare_text_delta(base, request, proof())) == raw


def test_noop_retains_exact_base_identity_generation_and_no_mutation_or_patch():
    before, _ = workspace()
    base = response(before)
    base.generation = RichGenerationState(id='controlled-generation', status='running', stage='assemble', errorCode=None)
    original = before.project.document.regions[2].blocks[0].content[0]
    result = prepare_text_delta(base, command(before, text=original.text[:6]), proof())
    assert result.mutation_wire is None and result.workspace_patch == []
    assert result.base_snapshot == result.result_snapshot and result.base_workspace_sha256 == result.result_workspace_sha256
    assert result.result_identity == base.identity and result.result_generation == base.generation
    assert not any(result.created_ids.values())


@pytest.mark.parametrize('change', ['base', 'package', 'identity'])
def test_unbound_base_package_or_derived_metadata_cannot_supply_a_delta(change):
    before, _ = workspace(); base = response(before)
    full = prepare_text_edit(base, command(before), proof())
    if change == 'base':
        base.workspace.project.document.regions[2].blocks[0].content[0].text += 'changed'
    elif change == 'package':
        package = full.preview.workspace.project.template_package
        package.original_format = 'yaml' if package.original_format == 'json' else 'json'
    else:
        full.preview.identity.title = 'Forged result identity'
    with pytest.raises(ValueError):
        prepared_delta(base, full)


@pytest.mark.parametrize('change', ['mutation_wire', 'client_id', 'result_revision', 'duplicate_ids', 'presentation_overlap'])
def test_delta_wire_binds_its_mutation_capture_identity_and_disjoint_reference_patch(change):
    before, _ = workspace()
    delta = prepare_text_delta(response(before), command(before), proof())
    value = delta.model_dump(mode='json', by_alias=True)
    if change == 'mutation_wire':
        value['mutationWire'] += ' '
    elif change == 'client_id':
        value['clientMutationId'] = 'unrelated-request'
    elif change == 'result_revision':
        value['resultSnapshot']['projectRevision'] = value['baseSnapshot']['projectRevision']
    elif change == 'duplicate_ids':
        value['createdIds'] = {'text': {'a': 'duplicate', 'b': 'duplicate'}}
    else:
        ref = before.project.document.regions[2].blocks[0].presentation.model_dump(mode='json', by_alias=True)
        value['presentationPatch']['set'] = {'block-paper-a': ref}
        value['presentationPatch']['remove'] = ['block-paper-a']
    with pytest.raises(ValueError):
        TemplatePreparedEditDeltaV1.model_validate(value)


def test_delta_payload_enforces_existing_budget_before_any_retention(monkeypatch):
    before, _ = workspace()
    monkeypatch.setattr(template_delta, 'LIMITS', replace(template_delta.LIMITS, proposal_bytes=1))
    with pytest.raises(BackgroundFailure, match='JOB_STORAGE_FULL'):
        prepare_text_delta(response(before), command(before), proof())
