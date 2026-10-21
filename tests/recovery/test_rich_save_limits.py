"""Exact transport budgets and durable recovery for atomic rich edits."""

import errno
import json
from pathlib import Path
import sys

import httpx
import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core import rich_project_store
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.rich_archive import export_rich_archive, open_rich_archive
from packages.resume_core.rules import RulesStore
from resume_api.app import create_app
from resume_api.gui_projects import ProjectFailure
from resume_api.rich_projects import RichProjectService
from tests.recovery.generation_fixtures import frozen_now
from tests.recovery.test_rich_persistence import without_sources

MIB = 1024 * 1024


def edit(workspace, text="Saved 🛠", identifier="save"):
    block = workspace.project.document.regions[0].blocks[0]
    end = sum(len(span.text.encode("utf-16-le")) // 2 for span in block.content)
    return RichMutation.model_validate({"schemaVersion": 1, "projectId": workspace.project_id,
        "clientMutationId": identifier, "actionId": identifier, "kind": "typing",
        "capture": {"sessionId": "session", "actionId": identifier, "actionToken": 0, "dependencies": []},
        "steps": [{"kind": "replace_inline_range", "blockId": block.id, "cellId": None, "field": "content",
                   "start": 0, "end": end, "beforeRevision": block.revision,
                   "content": [{"type": "text", "text": text, "styles": {}}]}]})


def wire_bytes(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sized_request(workspace, size, character):
    data = edit(workspace, "").model_dump(by_alias=True)
    available = size - len(wire_bytes(data))
    width = len(character.encode("utf-8"))
    data["steps"][0]["content"][0]["text"] = character * (available // width) + "x" * (available % width)
    wire = wire_bytes(data)
    assert len(wire) == size
    return wire


def service(root):
    return RichProjectService(root / "operations", RulesStore(root / "store"), lambda: None, clock=frozen_now)


def seeded(root):
    instance = service(root)
    workspace = without_sources()
    instance.loaded = True
    instance.workspaces[workspace.project_id] = workspace
    assert instance.persist(workspace.project_id) == "durable"
    return instance, workspace


@pytest.mark.asyncio
@pytest.mark.parametrize("character", ["x", "я", "🛠"])
@pytest.mark.parametrize("offset", [-1, 0, 1])
async def test_authenticated_save_enforces_exact_utf8_budget_without_partial_writes(tmp_path, character, offset):
    origin = "http://127.0.0.1:39542"
    secret = "synthetic-save-budget-012345678901"
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("fixture")
    app = create_app(origin=origin, secret=secret, temp_root=tmp_path / "operations", dist=dist, data_root=tmp_path / "store")
    instance = app.app.state.rich_projects
    workspace = without_sources()
    identifier = workspace.project_id
    instance.loaded = True
    instance.workspaces[identifier] = workspace
    assert instance.persist(identifier) == "durable"
    snapshot = tmp_path / "store/projects" / identifier / "workspace.json"
    before = snapshot.read_bytes()
    wire = sized_request(workspace, MIB + offset, character)
    if offset <= 0:
        assert len(RichMutation.model_validate_json(wire).model_dump_json(by_alias=True).encode("utf-8")) == len(wire)
    else:
        with pytest.raises(ValidationError, match="1 MiB"):
            RichMutation.model_validate_json(wire)

    async def chunks():
        yield wire[:-1]
        yield wire[-1:]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin) as client:
        headers = {"Origin": origin, "Content-Type": "application/json"}
        assert (await client.post("/v1/session/exchange", headers=headers, json={"secret": secret})).status_code == 200
        path = f"/v1/rich/projects/{identifier}/mutations"
        response = await client.post(path, headers=headers, content=chunks())
        assert response.status_code == (200 if offset <= 0 else 413)
        if offset > 0:
            assert snapshot.read_bytes() == before
            assert instance.read(identifier) == workspace
            assert not instance.read(identifier).mutation_replay
            response = await client.post(path, headers=headers, content=edit(workspace).model_dump_json(by_alias=True).encode())
            assert response.status_code == 200
        result = response.json()
        assert result["durability"] == "durable"
        assert result["savedDocumentRevision"] == workspace.document_revision + 1
        assert len(instance.read(identifier).mutation_replay) == 1
        restarted = service(tmp_path).read(identifier)
        assert restarted == instance.read(identifier)


@pytest.mark.parametrize("count", [1000, 1001])
def test_mutation_contract_enforces_the_step_boundary(count):
    data = edit(without_sources()).model_dump(by_alias=True)
    data["steps"] *= count
    assert len(wire_bytes(data)) < MIB
    if count == 1000:
        assert len(RichMutation.model_validate(data).steps) == 1000
    else:
        with pytest.raises(ValidationError, match="1000"):
            RichMutation.model_validate(data)


@pytest.mark.parametrize("failure", [errno.ENOSPC, errno.EACCES])
def test_failed_disk_write_retries_atomic_document_and_facts_once_and_survives_reopen(tmp_path, monkeypatch, failure):
    instance, original = seeded(tmp_path)
    identifier = original.project_id
    snapshot = tmp_path / "store/projects" / identifier / "workspace.json"
    before = snapshot.read_bytes()
    candidate = next(record for record in original.project.facts.records if record.kind == "candidate").model_copy(deep=True)
    candidate.title.raw_text = candidate.title.value = "Senior engineer"
    data = edit(original).model_dump(by_alias=True)
    data["steps"].append({"kind": "put_record", "beforeRevision": candidate.revision, "record": candidate.model_dump(by_alias=True)})
    request = RichMutation.model_validate(data)
    write = rich_project_store.atomic_write

    def failing(path, raw, **options):
        if path == snapshot:
            raise OSError(failure, "synthetic write failure")
        return write(path, raw, **options)

    with monkeypatch.context() as patch:
        patch.setattr(rich_project_store, "atomic_write", failing)
        failed = instance.mutate(identifier, request)
    assert failed.durability == "failed" and failed.save_error == "PROJECT_SAVE_FAILED"
    assert failed.saved_document_revision == original.document_revision
    assert failed.workspace.project.document.regions[0].blocks[0].content[0].text == "Saved 🛠"
    assert next(r for r in failed.workspace.project.facts.records if r.id == candidate.id).title.value == "Senior engineer"
    assert snapshot.read_bytes() == before
    assert service(tmp_path).read(identifier) == original

    saved = instance.mutate(identifier, request)
    assert saved.durability == "durable" and saved.save_error is None
    assert saved.saved_document_revision == original.document_revision + 1
    assert len(saved.workspace.mutation_replay) == 1
    assert instance.mutate(identifier, request).workspace == saved.workspace
    assert service(tmp_path).read(identifier) == saved.workspace
    archive = export_rich_archive(saved.workspace, {}, {}, {})
    restored, _, _, _ = open_rich_archive(archive, "restored")
    assert restored.project.document == saved.workspace.project.document
    assert restored.project.facts == saved.workspace.project.facts


def test_stale_fact_in_composite_save_never_commits_the_document_half(tmp_path):
    instance, original = seeded(tmp_path)
    identifier = original.project_id
    snapshot = tmp_path / "store/projects" / identifier / "workspace.json"
    before = snapshot.read_bytes()
    candidate = next(record for record in original.project.facts.records if record.kind == "candidate").model_copy(deep=True)
    candidate.title.raw_text = candidate.title.value = "Rejected title"
    data = edit(original, "Must remain unsaved").model_dump(by_alias=True)
    data["steps"].append({"kind": "put_record", "beforeRevision": candidate.revision + 1, "record": candidate.model_dump(by_alias=True)})
    with pytest.raises(ProjectFailure, match="STALE_MUTATION"):
        instance.mutate(identifier, RichMutation.model_validate(data))
    assert instance.read(identifier) == original
    assert snapshot.read_bytes() == before
    assert service(tmp_path).read(identifier) == original
