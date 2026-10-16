"""Reached storage and cache cutpoints, then recovery through a fresh controller."""

import pytest

from packages.resume_core.background_store import BackgroundFailure, JobStore
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.rich_project_store import RichProjectStore
from tests.recovery.test_background_publication_crashes import attach
from tests.recovery.test_background_writers import projects_for
from tests.support.background_publication import PublicationFixture

CUTS = [(f"NB-D01:v{number:02d}", phase, side, writer)
    for start, phase in ((13, "assets_staged"), (37, "registry_cache_update"), (45, "tombstone_cleanup"))
    for number, side, writer in ((start, "before", "clean_detached"), (start + 1, "before", "attached_uncertain"),
        (start + 2, "after", "clean_detached"), (start + 3, "after", "attached_uncertain"))]


@pytest.mark.parametrize("variant,phase,side,writer", CUTS, ids=[item[0] for item in CUTS])
def test_storage_and_cache_cut_recovers_without_losing_canonical_truth(tmp_path, variant, phase, side, writer):
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    job, proposal, _batch = fixture.accepted()
    if writer == "attached_uncertain":
        attach(fixture)
    target = "before_" + phase if side == "before" else phase
    reached = []
    def fail(name, project):
        if name == target:
            reached.append(project)
            raise OSError("Synthetic cut at " + name)
    fixture.coordinator.observer = fail
    if phase == "tombstone_cleanup":
        fixture.canonical.tombstone(fixture.project)
        fixture.jobs.mark_deleted(fixture.project)
        try:
            fixture.canonical.cleanup_deleted(fixture.project)
        except (OSError, ProjectStoreFailure):
            pass
        fresh = RichProjectStore(fixture.root)
        assert fresh.registry().entries[0].tombstoned
        assert fresh.cleanup_deleted(fixture.project).cleanup_status == "complete"
        assert not (fresh.projects / fixture.project).exists()
        with pytest.raises(BackgroundFailure, match="PROJECT_DELETED"):
            JobStore(fixture.root).load(fixture.project)
    else:
        try:
            service.background_jobs.publication.publish(fixture.project, job.id, proposal.payload_sha256)
        except (OSError, BackgroundFailure):
            pass
        fresh = fixture.fresh()
        recovered = fresh.coordinator.recover(fixture.project)
        saved = phase == "registry_cache_update"
        observed = fresh.jobs.read(fixture.project, job.id)
        assert (observed.receipt is not None) == saved
        assert len(fresh.current().mutation_replay) == int(saved)
        assert fresh.coordinator.recover(fixture.project) == recovered
        controller = projects_for(fresh, tmp_path / "restarted")
        assert controller.read(fixture.project) == fresh.current()
        if saved:
            assert fresh.publish(job, proposal).receipt == observed.receipt
    assert reached == [fixture.project], variant
