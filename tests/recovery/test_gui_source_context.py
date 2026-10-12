"""Located read-only context and shared captured-selection boundaries."""

from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_selection import field_index, selection_fingerprint, utf16_slice, valid_selection
from packages.resume_core.gui_source_context import source_context
from packages.resume_core.gui_annotations import initial_annotations
from packages.resume_core.models.recovery import Selection, SourceContextRequest
from resume_api.app import create_app
from tests.recovery.generation_fixtures import CreationProvider, frozen_now, render_workspace
from tests.recovery.test_gui_annotations import annotations
from tests.recovery.test_gui_projects import finish
from tests.recovery.candidate_fixtures import ROOT


def query(workspace, field_ids=None, selection=None):
    return SourceContextRequest(projectId=workspace.project_id, documentRevision=workspace.document_revision,
        fieldIds=field_ids or [], selection=selection)


def selection(workspace, spans):
    return Selection(projectId=workspace.project_id, documentRevision=workspace.document_revision,
        dependencyFingerprint=selection_fingerprint(workspace), spans=spans)


def span(id, text, start=0, end=None):
    return {"fieldId": id, "range": {"start": start, "end": len(text.encode("utf-16-le")) // 2 if end is None else end}, "capturedText": text}


def test_e1_job_source_read_returns_field_and_block_evidence_without_mutation():
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    before = workspace.model_dump()
    result = source_context(workspace, query(workspace, [job.context.field_id]))
    assert result.status == "evidence" and workspace.model_dump() == before
    assert any(item.evidence.text == "Сервис обработки заказов." and item.relation == "field" for item in result.excerpts)
    assert all(item.evidence.source_id == workspace.project.sources[0].id for item in result.excerpts)
    assert not any("CRM" in item.evidence.text or "Rust" in item.evidence.text for item in result.excerpts)
    dates = source_context(workspace, query(workspace, [job.periods[0].start_text.field_id]))
    assert any(item.relation == "block" for item in dates.excerpts)


def test_e2_empty_context_returns_broader_job_evidence_and_both_conflict_spans():
    workspace = render_workspace("E2")
    request, draft, deps = annotations()
    workspace.annotations = initial_annotations(workspace.project_id, draft.document, request.normalized, [], deps)
    job = workspace.project.document.jobs[0]
    result = source_context(workspace, query(workspace, [job.context.field_id]))
    assert result.status == "evidence" and {item.relation for item in result.excerpts} == {"block"}
    assert {item.evidence.text for item in result.excerpts} >= {"пять", "шесть", "Python", "ExampleDB-X"}
    assert {mark.code for mark in result.annotations} == {"missing_job_dates", "team_size_conflict"}
    assert all("Дельта" not in item.evidence.text and "Rust" not in item.evidence.text for item in result.excerpts)


def test_exact_literal_selection_has_exact_relation_and_user_addition_has_no_invented_source():
    workspace = render_workspace("E2")
    field = workspace.project.document.jobs[1].stack
    captured = selection(workspace, [span(field.field_id, "SQL")])
    result = source_context(workspace, query(workspace, selection=captured))
    assert any(item.relation == "exact" and item.evidence.text == "SQL" for item in result.excerpts)
    field.text, field.origin = "Added by user", "user"
    # Historical references do not establish evidence for newly authored text.
    result = source_context(workspace, query(workspace, [field.field_id]))
    assert result.status == "user-origin" and result.excerpts == []
    field.origin, field.fact_ids, field.evidence = "migration", [], []
    result = source_context(workspace, query(workspace, ["candidate/location"]))
    assert result.status == "no-evidence" and result.excerpts == []


@pytest.mark.parametrize("change", ["project", "revision", "fingerprint", "text", "range", "unknown-field", "duplicate", "source-revision", "fact-revision"])
def test_stale_or_mismatched_capture_returns_no_excerpt(change):
    workspace = render_workspace()
    field = workspace.project.document.profile.text
    captured = selection(workspace, [span(field.field_id, field.text)])
    if change == "project": captured.project_id = "different"
    if change == "revision": captured.document_revision += 1
    if change == "fingerprint": captured.dependency_fingerprint = "b" * 64
    if change == "text": captured.spans[0].captured_text = "Different"
    if change == "range": captured.spans[0].range.end += 100
    if change == "unknown-field": captured.spans[0].field_id = "missing/field"
    if change == "duplicate": captured.spans.append(captured.spans[0].model_copy(deep=True))
    if change == "source-revision": workspace.project.sources[0].revision += 1
    if change == "fact-revision": workspace.project.facts[0].revision += 1
    result = source_context(workspace, query(workspace, selection=captured))
    assert result.status == "stale" and result.excerpts == result.annotations == []


def test_utf16_capture_preserves_emoji_newlines_and_rejects_surrogate_splits():
    workspace = render_workspace()
    field = workspace.project.document.profile.text
    field.text = "A😀\r\n\r\nB"
    good = selection(workspace, [span(field.field_id, "😀\n\n", 1, 5)])
    assert valid_selection(workspace, good) and utf16_slice(field.text, 1, 5) == "😀\n\n"
    for start, end in [(1, 2), (2, 3), (0, 100)]:
        bad = selection(workspace, [span(field.field_id, "x", start, end)])
        assert not valid_selection(workspace, bad)


def test_cross_field_capture_requires_order_and_all_nonempty_intervening_fields():
    workspace = render_workspace()
    fields = list(field_index(workspace.project.document).values())[:4]
    first, last = fields[0][0], fields[-1][0]
    spans = [span(field.field_id, field.text) for field, _ in fields if field.text]
    good = selection(workspace, spans)
    assert valid_selection(workspace, good)
    assert not valid_selection(workspace, selection(workspace, [span(last.field_id, last.text), span(first.field_id, first.text)]))
    assert not valid_selection(workspace, selection(workspace, [span(first.field_id, first.text), span(last.field_id, last.text)]))


def test_source_reference_and_literal_corruption_never_invent_excerpt():
    workspace = render_workspace()
    field = workspace.project.document.profile.text
    fact = next(fact for fact in workspace.project.facts if getattr(fact, "literal_evidence", None))
    field.fact_ids, field.evidence = [fact.id], []
    fact.literal_evidence[0].text = "Not in source"
    result = source_context(workspace, query(workspace, [field.field_id]))
    assert result.status == "no-evidence" and result.excerpts == []
    fact.literal_evidence[0].text = "Python"
    fact.literal_evidence[0].source_revision += 1
    result = source_context(workspace, query(workspace, [field.field_id]))
    assert result.status == "no-evidence" and result.excerpts == []
    assert source_context(workspace, query(workspace, ["unknown/field"])).status == "stale"


@pytest.mark.asyncio
async def test_protected_source_context_route_is_zero_call_and_checks_stale_revision(tmp_path):
    origin, secret = "http://127.0.0.1:39329", "synthetic-context-secret-0123456789"
    dist = tmp_path / "dist"; dist.mkdir()
    provider = CreationProvider()
    app = create_app(origin=origin, secret=secret, temp_root=tmp_path / "operations", dist=dist,
        data_root=tmp_path / "FoldCV", gui_provider=provider, gui_clock=frozen_now)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=origin) as client:
        headers = {"Origin": origin}
        await client.post("/v1/session/exchange", headers=headers, json={"secret": secret})
        created = (await client.post("/v1/projects", headers=headers, json={"text": (ROOT / "E1.txt").read_text()})).json()
        id = created["workspace"]["projectId"]
        workspace = await finish(app.app.state.gui_projects, id, created["generationId"])
        response = (await client.get(f"/v1/projects/{id}")).json()
        assert response["selectionFingerprint"] == selection_fingerprint(workspace)
        body = query(workspace, [workspace.project.document.jobs[0].context.field_id]).model_dump(by_alias=True)
        assert (await client.post(f"/v1/projects/{id}/source-context", json=body)).status_code == 403
        before = workspace.model_dump()
        for _ in range(3):
            response = await client.post(f"/v1/projects/{id}/source-context", headers=headers, json=body)
            assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
            assert response.json()["status"] == "evidence"
        assert len(provider.calls) == 2 and app.app.state.gui_projects.read(id).model_dump() == before
        body["documentRevision"] -= 1
        result = (await client.post(f"/v1/projects/{id}/source-context", headers=headers, json=body)).json()
        assert result["status"] == "stale" and result["excerpts"] == []
