"""Versioned HTTP responses keep authored snapshots and actual save outcomes coherent."""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_snapshot_merge import merge_snapshot
from packages.resume_core.rules import RulesStore
from packages.resume_core.template_api import TemplateProjectResponseV1
from packages.resume_core.template_assembly import assemble_template
from packages.resume_core.templates.compiler import canonical
from packages.resume_core.templates.presentation import snapshot_identity
from resume_api.gui_projects import ProjectFailure
from resume_api.rich_projects import RichProjectService
from resume_api.rich_routes import mount_rich_projects
from tests.templates.pipeline_fixtures import setup_operation, source_draft
from tests.templates.test_materialize import admitted, fallback_edit, issue_workspace


def isolated_service(tmp_path, workspace=None, sources=None):
    if workspace is None:
        workspace, sources = issue_workspace()
    def forbidden():
        raise AssertionError('HTTP snapshot/edit checks must not dispatch inference')
    service = RichProjectService(tmp_path / 'operations', RulesStore(tmp_path / 'store'), forbidden)
    service.loaded = True
    service.workspaces[workspace.project_id] = workspace.model_copy(deep=True)
    service.originals.update({(workspace.project_id, key): value for key, value in (sources or {}).items()})
    assert service.persist(workspace.project_id) == 'durable'
    return service, workspace.project_id


def application(service):
    app = FastAPI()
    def problem(code, status, _scope):
        return JSONResponse({'error': {'code': code}}, status_code=status)
    @app.exception_handler(ProjectFailure)
    async def project_error(_request, error):
        return problem(error.code, error.status, 'project')
    mount_rich_projects(app, service, problem)
    return app


@pytest.mark.asyncio
async def test_http_read_preview_mutate_save_and_reopen_keep_exact_snapshot_and_issues(tmp_path):
    service, identifier = isolated_service(tmp_path)
    path = '/v1/rich/projects/' + identifier
    disk = service.storage.read_committed(identifier)[0]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(service)), base_url='http://foldcv.test') as client:
        response = await client.get(path)
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        read = TemplateProjectResponseV1.model_validate(response.json())
        assert response.content == canonical(read)
        assert read.durability == 'durable' and read.snapshot == snapshot_identity(disk)
        assert read.workspace.schema_version == 7 and read.presentation.recipe == disk.project.template_package.recipe
        mutation = fallback_edit(read.workspace).model_dump(mode='json', by_alias=True)
        preview = await client.post(path + '/preview', json=mutation)
        assert preview.status_code == 200
        proposed = TemplateProjectResponseV1.model_validate(preview.json())
        assert proposed.durability == 'pending' and proposed.snapshot != read.snapshot
        assert proposed.saved_document_revision == read.workspace.document_revision
        assert [issue.state for issue in proposed.workspace.project.import_issues] == ['retired', 'active']
        assert canonical(service.storage.read_committed(identifier)[0]) == canonical(disk)
        changed = await client.post(path + '/mutations', json=mutation)
        assert changed.status_code == 200
        saved = TemplateProjectResponseV1.model_validate(changed.json())
        assert saved.durability == 'durable' and saved.snapshot == proposed.snapshot
        repeated = await client.post(path + '/mutations', json=mutation)
        assert repeated.status_code == 200 and repeated.json()['snapshot'] == changed.json()['snapshot']
        ack = await client.post(path + '/save', json={})
        assert ack.status_code == 200 and ack.json()['snapshot'] == changed.json()['snapshot']
    reopened = RichProjectService(tmp_path / 'reopened-workers', RulesStore(tmp_path / 'store'), lambda: None)
    restored = reopened.response(identifier)
    assert restored.snapshot == saved.snapshot and restored.presentation == saved.presentation
    assert restored.workspace.project.facts == disk.project.facts
    assert [issue.state for issue in restored.workspace.project.import_issues] == ['retired', 'active']


@pytest.mark.asyncio
async def test_http_failed_save_retains_prior_disk_and_pending_local_issue_edit_then_retries(tmp_path, monkeypatch):
    service, identifier = isolated_service(tmp_path)
    before = service.storage.read_committed(identifier)[0]
    mutation = fallback_edit(before)
    save = service.storage.save
    def fail(*_args, **_kwargs):
        raise ProjectStoreFailure('PROJECT_SAVE_FAILED')
    monkeypatch.setattr(service.storage, 'save', fail)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(service)), base_url='http://foldcv.test') as client:
        reply = await client.post('/v1/rich/projects/' + identifier + '/mutations',
            json=mutation.model_dump(mode='json', by_alias=True))
        assert reply.status_code == 200
        pending = TemplateProjectResponseV1.model_validate(reply.json())
        assert pending.durability == 'failed' and pending.save_error == 'PROJECT_SAVE_FAILED'
        assert pending.saved_document_revision == before.document_revision < pending.workspace.document_revision
        assert [issue.state for issue in pending.workspace.project.import_issues] == ['retired', 'active']
        assert canonical(service.storage.read_committed(identifier)[0]) == canonical(before)
        monkeypatch.setattr(service.storage, 'save', save)
        retry = await client.post('/v1/rich/projects/' + identifier + '/mutations',
            json=mutation.model_dump(mode='json', by_alias=True))
        assert retry.status_code == 200
        saved = TemplateProjectResponseV1.model_validate(retry.json())
        assert saved.durability == 'durable' and saved.snapshot == pending.snapshot


@pytest.mark.parametrize('change', ['snapshot', 'presentation', 'workspace', 'save_ack'])
def test_response_rejects_mismatched_workspace_snapshot_presentation_or_durable_ack(tmp_path, change):
    service, identifier = isolated_service(tmp_path)
    value = service.response(identifier).model_dump(mode='json', by_alias=True)
    if change == 'snapshot':
        value['snapshot']['factsHash'] = '0' * 64
    elif change == 'presentation':
        value['presentation']['recipe']['style']['page']['first_body_top'] += 1
    elif change == 'workspace':
        value['workspace']['project']['document']['revision'] += 1
        value['workspace']['documentRevision'] += 1
    else:
        value['savedDocumentRevision'] += 1
    with pytest.raises(ValueError):
        TemplateProjectResponseV1.model_validate(value)


def test_template_predraft_has_null_presentation_and_legacy_response_keeps_its_wire(tmp_path):
    operation, _command, package, src, facts = setup_operation()
    before = source_draft(operation, facts, captured=package, src=src)
    raw = src.units[0].text.encode()
    service, identifier = isolated_service(tmp_path, before, {src.id: raw})
    response = service.response(identifier)
    assert response.workspace.schema_version == 7 and response.snapshot is None and response.presentation is None
    assert response.durability == 'durable'
    from tests.recovery.test_rich_persistence import without_sources
    legacy = without_sources()
    legacy_service, legacy_id = isolated_service(tmp_path / 'legacy', legacy)
    value = legacy_service.response(legacy_id).model_dump(mode='json', by_alias=True)
    assert value['workspace']['schemaVersion'] == 6 and 'snapshot' not in value and 'schemaVersion' not in value


def test_metadata_merge_preserves_template_workspace_version_and_newer_document():
    operation, facts, package, src, _raw = admitted()
    base = assemble_template(source_draft(operation, facts, captured=package, src=src), operation)
    proposed = base.model_copy(deep=True)
    proposed.title = 'Local catalog title'
    proposed.project_revision += 1
    proposed.project.revision = proposed.project_revision
    current = base.model_copy(deep=True)
    current.project.document.revision += 1
    current.document_revision = current.project.document.revision
    current.project_revision += 1
    current.project.revision = current.project_revision
    current.project.document.regions[2].blocks[0].revision += 1
    merged = merge_snapshot(base, proposed, current)
    assert merged.schema_version == 7 and merged.title == proposed.title
    assert merged.project.document == current.project.document and merged.project.template_package == package
    assert merged.project_revision == base.project_revision + 2
