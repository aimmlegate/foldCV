"""Generic extension storage, human authority and corrupt portable inputs."""

import json
from pathlib import Path

import pytest

from packages.resume_core.gui_archive_zip import ArchiveFailure, digest, read_zip, write_zip
from packages.resume_core.models.template_workspace import WorkspaceV7
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.rich_project_store import RichProjectStore, decode_rich_snapshot
from packages.resume_core.template_facts import ambiguous_edit, human_edit
from packages.resume_core.template_inverse import inverse_template_mutation
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.templates.compiler import canonical, compile_bytes, sha256
from packages.resume_core.templates.projection import SchemaFailure, validate_payload
from packages.resume_core.templates.store import BUNDLED_TEMPLATE
from tests.templates.storage_fixtures import PAPER_SCHEMA, workspace
from tests.templates.test_transactions import authorization, extension_step, request


def test_restart_and_portable_transfer_keep_exact_sources_cells_and_package(tmp_path):
    original, sources = workspace()
    original.project.facts = human_edit(original.project.facts, 'paper-a', 'year', 'forthcoming')
    original.project.facts = human_edit(original.project.facts, 'paper-b', 'status', 'submitted')
    store = RichProjectStore(tmp_path / 'first')
    store.save(original, {(original.project_id, key): value for key, value in sources.items()}, {})
    loaded, failures, _ = RichProjectStore(tmp_path / 'first').load_all()
    recovered, originals, _, images = loaded[original.project_id]
    assert not failures and recovered == original and not images
    assert originals == {(original.project_id, key): value for key, value in sources.items()}
    data = export_rich_archive(recovered, sources, {}, {})
    moved, retained, artifacts, images = open_rich_archive(data, 'portable-copy')
    expected = original.model_copy(deep=True)
    expected.project_id = expected.project.project_id = 'portable-copy'
    assert moved == expected and retained == sources and not artifacts and not images
    second = RichProjectStore(tmp_path / 'second')
    second.save(moved, {(moved.project_id, key): value for key, value in retained.items()}, {})
    assert RichProjectStore(tmp_path / 'second').load_all()[0]['portable-copy'][0] == moved
    assert moved.project.template_package == original.project.template_package
    year = moved.project.facts.extensions[0].cells[2]
    status = moved.project.facts.extensions[1].cells[4]
    assert (year.raw_input, year.typed_value, year.state) == ('forthcoming', None, 'human_raw')
    assert (status.raw_input, status.typed_value, status.state) == ('submitted', None, 'human_raw')


@pytest.mark.parametrize('corruption', ['missing_font', 'missing_bound_record', 'missing_provenance_record',
    'duplicate_source', 'undeclared_relation'])
def test_corrupt_portable_fails_before_destination_publication(tmp_path, corruption):
    original, sources = workspace()
    files = read_zip(export_rich_archive(original, sources, {}, {}))
    manifest = json.loads(files['manifest.json'])
    if corruption == 'missing_font':
        font = next(asset for asset in original.project.template_package.assets if asset.role == 'font')
        missing = 'template/assets/' + font.sha256
        del files[missing]
        manifest['entries'] = [entry for entry in manifest['entries'] if entry['path'] != missing]
    else:
        value = json.loads(files['workspace.json'])
        project = value['project']
        block = project['document']['regions'][2]['blocks'][0]
        if corruption == 'missing_bound_record':
            block['content'][0]['recordId'] = 'missing-record'
        elif corruption == 'missing_provenance_record':
            block['provenance'] = [{'kind': 'field_binding', 'id': 'dangling',
                'recordId': 'missing-record', 'fieldKey': 'title'}]
        elif corruption == 'duplicate_source':
            project['sources'].append(project['sources'][0])
        else:
            relation = {'id': 'undeclared-relation', 'kind': 'owned_by', 'subjectId': 'paper-a',
                'targetId': 'paper-b', 'revision': 1, 'active': True}
            project['facts']['relations'] = [relation]
            project['facts']['extensions'][0]['relations'] = [relation]
        files['workspace.json'] = json.dumps(value).encode()
        entry = next(entry for entry in manifest['entries'] if entry['path'] == 'workspace.json')
        entry.update(size=len(files['workspace.json']), sha256=digest(files['workspace.json']))
    files['manifest.json'] = json.dumps(manifest).encode()
    destination = tmp_path / 'destination'
    with pytest.raises(ArchiveFailure):
        restored, originals, artifacts, images = open_rich_archive(write_zip(files), 'must-not-exist')
        RichProjectStore(destination).save(restored, originals, artifacts, images)
    assert not destination.exists()
    assert original.project.document.regions[2].blocks[0].content[0].record_id == 'paper-a'


def test_model_assertions_reject_raw_human_values_but_persistence_never_rechecks_them(monkeypatch):
    original, _ = workspace()
    bad = {'title': 'Shared title', 'journal': None, 'year': 'forthcoming', 'url': None, 'status': 'submitted'}
    with pytest.raises(SchemaFailure):
        validate_payload(PAPER_SCHEMA, bad)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('dynamic semantic validation must not run for human persistence')
    monkeypatch.setattr('packages.resume_core.templates.projection.validate_payload', forbidden)
    prior = original.project.facts.model_copy(deep=True)
    edited = human_edit(prior, 'paper-a', 'year', 'forthcoming')
    original.project.facts = edited
    assert WorkspaceV7.model_validate_json(original.model_dump_json(by_alias=True)) == original
    original.project.facts = prior
    changed, _ = apply_rich_mutation(original, request(original, [extension_step(original, edited.extensions[0])]))
    inverse = inverse_template_mutation(original, changed, origin_action_id='human-edit',
        mutation_id='undo-year', session_id='session', action_token=2)
    undo, _ = apply_rich_mutation(changed, inverse, history_authorization=authorization(changed, inverse))
    assert undo.project.facts.extensions[0].cells[2].typed_value == 2024
    assert undo.project.facts.extensions[0].cells[2].revision > changed.project.facts.extensions[0].cells[2].revision
    redo = inverse_template_mutation(changed, undo, origin_action_id='human-edit',
        mutation_id='redo-year', session_id='session', action_token=3, kind='redo')
    redone, _ = apply_rich_mutation(undo, redo, history_authorization=authorization(undo, redo))
    assert redone.project.facts.extensions[0].cells[2].typed_value is None
    assert redone.project.facts.extensions[0].cells[2].raw_input == 'forthcoming'
    assert redone.project.facts.extensions[1] == prior.extensions[1]


def test_ambiguous_edit_retains_one_scope_without_stale_typed_claims():
    original, _ = workspace()
    facts = ambiguous_edit(original.project.facts, ['a-title', 'a-journal'], 'Exact human replacement',
        'edit-action', ['block-paper-a'], scope_id='manual-scope')
    assert len(facts.manual_scopes) == 1
    assert facts.manual_scopes[0].raw_input == 'Exact human replacement'
    assert [(c.state, c.typed_value, c.manual_scope_id) for c in facts.extensions[0].cells[:2]] == [
        ('pending_manual', None, 'manual-scope'), ('pending_manual', None, 'manual-scope')]
    assert facts.extensions[0].cells[2] == original.project.facts.extensions[0].cells[2]
    original.project.facts = facts
    assert WorkspaceV7.model_validate_json(original.model_dump_json(by_alias=True)) == original


def test_unknown_wire_version_fails_without_touching_old_bytes(tmp_path):
    old = Path('tests/fixtures/rich_workspace.json').read_bytes()
    path = tmp_path / 'prototype.json'
    path.write_bytes(old)
    assert decode_rich_snapshot(old).schema_version == 6
    value = json.loads(old)
    value['schemaVersion'] = 999
    with pytest.raises(ProjectStoreFailure, match='PROJECT_VERSION_UNSUPPORTED'):
        decode_rich_snapshot(json.dumps(value).encode())
    assert path.read_bytes() == old


def test_coverage_retains_builtin_discovery_handles():
    original, _ = workspace()
    data = original.model_dump(by_alias=True)
    project = data['project']
    config = original.project.template_package.definition.model_dump(by_alias=True)
    config['fact_types'].append({'id': 'candidate-type', 'schema_version': '1', 'builtin_kind': 'candidate',
        'relations': [], 'schema': {'type': 'object', 'additionalProperties': False,
            'required': ['name'], 'properties': {'name': {'type': 'string'}}}})
    captured = compile_bytes(canonical(config), BUNDLED_TEMPLATE.parent, original_format='json')
    project['templatePackage'] = captured.model_dump(by_alias=True)
    for block in project['document']['regions'][2]['blocks']:
        block['presentation']['packageHash'] = captured.package_hash
        block['content'][0]['presentation']['packageHash'] = captured.package_hash
    field = lambda text: {'value': text, 'rawText': text, 'status': 'known', 'revision': 1, 'pendingRawText': None}
    project['facts']['records'] = [{'id': 'candidate', 'revision': 1, 'origin': 'source', 'evidence': [],
        'kind': 'candidate', 'name': field('Alex Example'), 'title': field('Engineer'), 'location': field('Example City')}]
    model = {'adapter': 'fixture', 'model': 'fixture', 'effort': 'medium', 'capabilityProfile': 'fixture',
        'capabilityVersion': '1', 'configurationHash': sha256(b'fixture')}
    project['templateOperations'] = [{'schemaVersion': 1, 'id': 'operation', 'projectId': original.project_id,
        'capture': {'packageHash': captured.package_hash,
            'sourceHashes': {s.id: s.byte_sha256 for s in original.project.sources}, 'factRevisions': {},
            'authorityHash': sha256(b'authority'), 'dependencyHash': sha256(b'dependencies'),
            'allowTextRewrite': False, 'primary': model, 'fallback': None,
            'formattingAsOf': data['formattingAsOf'], 'policy': {'callCap': 1, 'concurrency': 1,
                'processingSeconds': 300, 'cleanupSeconds': 5, 'finalizationSeconds': 30,
                'primaryRepairs': 1, 'fallbackRepairs': 1}},
        'state': 'captured', 'admittedAt': None, 'expiresAt': None, 'lastObservedAt': None,
        'tasks': [], 'allocations': [{'operationId': 'operation', 'taskId': 'candidate-task',
            'discoveryAttemptId': 'source-discovery', 'key': 'candidate', 'semanticType': 'candidate-type',
            'discoveryHash': sha256(b'candidate-discovery'), 'itemHandle': 'builtin-handle',
            'recordId': 'candidate', 'cellIds': {'name': 'candidate-name'}}],
        'attempts': [], 'proposals': [], 'reviewInputs': [], 'receipts': [], 'finalization': None,
        'publication': {'state': 'pending', 'intentId': None, 'workspaceHash': None, 'errorCode': None},
        'exportAttempts': []}]
    span = project['facts']['extensions'][0]['cells'][0]['evidence'][0]
    project['importCoverage'] = [{'span': span, 'itemHandle': 'builtin-handle', 'blockIds': [],
        'disposition': 'source_only', 'reason': 'Retained source record'}]
    assert WorkspaceV7.model_validate(data).project.import_coverage[0].item_handle == 'builtin-handle'
    project['importCoverage'][0]['itemHandle'] = 'unknown-handle'
    with pytest.raises(ValueError, match='missing source coverage target'):
        WorkspaceV7.model_validate(data)
