"""Non-HTTP callbacks use the same writer boundary as the mounted routes."""

import asyncio

import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_panel import RichPanelRequest
from packages.resume_core.rich_timeline import CascadeRequest, CascadeApplyRequest, cascade_proposal, cascade_mutation
from tests.recovery.test_background_assets import image_fixture, reclaim
from tests.recovery.test_background_exports import HeldRenderer
from tests.recovery.test_background_fixed_storage import accepted_fixed
from tests.recovery.test_background_inverse import block, mutation, put
from tests.recovery.test_background_writer_routes import independent
from tests.recovery.test_background_writers import projects_for
from tests.recovery.test_rich_synchronization import capture
from tests.recovery.test_rich_timeline import timeline
from tests.support.background_publication import PublicationFixture


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [f"NB-P08:v{index:02d}" for index in range(25, 30)])
async def test_internal_writer_inventory_has_no_unguarded_callback(tmp_path, variant):
    if variant == "NB-P08:v27":
        from packages.resume_core.background_limits import LIMITS
        fixture, service, clock, _aid, path = await image_fixture(tmp_path)
        committed = independent(fixture)
        clock.advance(LIMITS.orphan_asset_seconds)
        reclaim(fixture, service)
        assert not path.exists() and not fixture.current().project.assets
        assert fixture.current().project.document == committed.project.document
        assert fixture.jobs.load(fixture.project).history.workspace_sha256 == digest_bytes(fixture.current())
        return
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    if variant == "NB-P08:v25":
        operation = service.new_operation(fixture.project, "render")
        committed = independent(fixture)
        operation.status = "completed"
        assert service.persist(fixture.project) == "durable"
        assert fixture.current().project.document == committed.project.document
        assert fixture.current().project.operations[0].status == "completed"
        with pytest.raises(ProjectStoreFailure, match="PROJECT_COORDINATOR_REQUIRED"):
            fixture.canonical.save(service.read(fixture.project), {}, {})
    elif variant == "NB-P08:v26":
        operation = service.new_operation(fixture.project, "rewrite_prose")
        operation.status = "running"; assert service.persist(fixture.project) == "durable"
        committed = independent(fixture)
        restarted = projects_for(fixture, tmp_path / "restart")
        assert restarted.read(fixture.project).project.document == committed.project.document
        assert restarted.read(fixture.project).project.operations[0].status == "interrupted"
        second = PublicationFixture(tmp_path / "fixed-recovery")
        _service, job, proposal, _record = accepted_fixed(second)
        before = second.current()
        after_restart = projects_for(second, tmp_path / "restart-fixed")
        assert after_restart.read(second.project) == before and before.sync_records[-1].ready
        assert second.jobs.read(second.project, job.id).proposal_id == proposal.id
    elif variant == "NB-P08:v28":
        renderer = HeldRenderer(); service.renderer = renderer
        before = fixture.current()
        task = asyncio.create_task(service.export(fixture.project))
        await asyncio.wait_for(renderer.entered.wait(), 10)
        committed = independent(fixture)
        renderer.release.set()
        snapshot, blob = await asyncio.wait_for(task, 10)
        current = fixture.current()
        assert snapshot.document_revision == before.document_revision and blob
        assert current.project.document == committed.project.document
        assert current.project.renders[0] == snapshot and current.project.operations[0].status == "completed"
        assert not service.tasks and not service.files
    else:
        independent(fixture)
        before = fixture.current()
        path = fixture.jobs.projects / fixture.project / "state.json"
        raw = path.read_bytes()
        request = mutation(before, [put(before, "narrative")], "preview-only")
        assert service.preview(fixture.project, request).workspace.project.document != before.project.document
        panel = RichPanelRequest(operation="edit", recordId="language-1", recordKind="language", values={"level": "C2"},
            factsRevision=before.project.facts.revision, documentRevision=before.document_revision, capture=capture())
        assert service.panel_preview(fixture.project, panel).workspace.project.facts != before.project.facts
        assert fixture.current() == before and path.read_bytes() == raw
        other = PublicationFixture(tmp_path / "cascade")
        value = timeline([("A", "a", "2020-01", "2020-04"), ("B", "b", "2020-04", "2020-06")])
        other.snapshot(lambda workspace: setattr(workspace, "project", value.project.model_copy(deep=True)), "timeline")
        controller = projects_for(other, tmp_path / "cascade-controller")
        current = other.current()
        state_path = other.jobs.projects / other.project / "state.json"
        raw = state_path.read_bytes()
        captured = CascadeRequest(anchorJobId="A", anchorPeriodId="a", capture=capture())
        proposed = cascade_proposal(controller.read(other.project), captured)
        assert proposed.status == "available"
        cascade = CascadeApplyRequest(proposal=proposed, capture=capture())
        assert controller.preview(other.project, cascade_mutation(current, cascade)).workspace.project.facts != current.project.facts
        assert other.current() == current and state_path.read_bytes() == raw
