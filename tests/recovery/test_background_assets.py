"""Real image bytes survive every owner and both pin/GC orders."""

import asyncio
from datetime import datetime, timedelta
import threading

import pytest

from packages.resume_core.background_assets import JobAssets
from packages.resume_core.background_limits import LIMITS
from packages.resume_core.background_retention import JobRetention
from packages.resume_core.background_store import BackgroundFailure
from tests.recovery.test_background_store import capture as job_capture
from tests.recovery.test_background_writers import projects_for
from tests.recovery.test_rich_images_service import capture, png, refs
from tests.support.background_publication import PublicationFixture


class Time:
    def __init__(self, value):
        self.value = datetime.fromisoformat(value)

    def __call__(self):
        return self.value.isoformat()

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


async def image_fixture(root):
    fixture = PublicationFixture(root)
    clock = Time(fixture.jobs.clock())
    fixture.jobs.clock = clock
    service = projects_for(fixture, root)
    refs(service, fixture.project, 1)
    identifier = await service.ingest_image(fixture.project, png(), capture())
    asset = fixture.current().project.assets[0]
    fixture.images = service.images
    service.image_sessions[(fixture.project, "session")].pending.clear()
    refs(service, fixture.project, 2)
    return fixture, service, clock, identifier, fixture.canonical.projects / fixture.project / asset.path


def reclaim(fixture, service):
    with service.state_lock:
        service.reclaim_images(fixture.project)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [f"NB-A01:v{index:02d}" for index in range(1, 8)])
async def test_owned_asset_pins_and_gc_have_a_valid_serial_order(tmp_path, variant):
    fixture, service, clock, aid, path = await image_fixture(tmp_path)
    assets = JobAssets(fixture.jobs)
    release = None
    if variant in {"NB-A01:v01", "NB-A01:v05"}:
        job, _ = fixture.jobs.submit(job_capture(fixture.jobs.load(fixture.project), "active-owner"))
        release = lambda: fixture.jobs.cancel(fixture.project, job.id)
    elif variant == "NB-A01:v02":
        job, proposal, _batch = fixture.accepted()
        assert job.publication == "waiting_for_sync"
        release = lambda: fixture.jobs.cancel(fixture.project, job.id)
    elif variant == "NB-A01:v04":
        job, proposal, _batch = fixture.accepted()
        assert fixture.publish(job, proposal).receipt.durable
        release = lambda: JobRetention(fixture.jobs).sweep(fixture.project)
    elif variant != "NB-A01:v07":
        assets.capture(fixture.project, "export", "export-owner", images={aid}, sources=[])
        release = lambda: assets.release(fixture.project, "export", "export-owner")
    if variant == "NB-A01:v05":
        for owner in ("first-export", "second-export"):
            assets.capture(fixture.project, "export", owner)
        assets.release(fixture.project, "export", "first-export")
        assets.release(fixture.project, "export", "second-export")
    clock.advance(LIMITS.orphan_asset_seconds)
    reclaim(fixture, service)
    if variant == "NB-A01:v07":
        assert not path.exists() and not fixture.current().project.assets
        with pytest.raises(BackgroundFailure, match="JOB_SCOPE_INVALID"):
            assets.capture(fixture.project, "export", "too-late", images={aid}, sources=[])
        assert not fixture.jobs.load(fixture.project).asset_pins
        return
    assert path.read_bytes() == service.images[(fixture.project, aid)]
    if variant == "NB-A01:v04":
        assert fixture.jobs.load(fixture.project).inverses[0].owner == "backend"
    release()
    reclaim(fixture, service)
    assert path.exists()
    clock.advance(LIMITS.orphan_asset_seconds)
    reclaim(fixture, service)
    assert not path.exists() and not fixture.current().project.assets
    assert (fixture.project, aid) not in service.images
    if variant == "NB-A01:v04":
        assert fixture.jobs.read(fixture.project, job.id).undo_expired


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-A02:v04", "NB-A02:v05"])
async def test_deduplicated_bytes_stay_owned_by_each_sharing_job(tmp_path, variant):
    fixture, service, clock, aid, path = await image_fixture(tmp_path)
    refs(service, fixture.project, 3)
    duplicate = await service.ingest_image(fixture.project, png(), capture(3, "duplicate"))
    assert duplicate == aid and len(fixture.current().project.assets) == 1
    service.image_sessions[(fixture.project, "session")].pending.clear()
    refs(service, fixture.project, 4)
    context = fixture.jobs.load(fixture.project)
    first, _ = fixture.jobs.submit(job_capture(context, "sharing-one"))
    second, _ = fixture.jobs.submit(job_capture(context, "sharing-two"))
    if variant == "NB-A02:v05":
        fixture.jobs.cancel(fixture.project, first.id)
    clock.advance(LIMITS.orphan_asset_seconds)
    reclaim(fixture, service)
    assert path.exists() and JobAssets(fixture.jobs).bytes_for(fixture.project, "job", second.id)[0][aid] == path.read_bytes()
    fixture.jobs.cancel(fixture.project, first.id)
    reclaim(fixture, service)
    assert path.exists()
    fixture.jobs.cancel(fixture.project, second.id)
    reclaim(fixture, service)
    clock.advance(LIMITS.orphan_asset_seconds)
    reclaim(fixture, service)
    assert not path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["NB-A02:v01", "NB-A02:v02", "NB-A02:v03"])
async def test_late_or_uncertain_upload_never_publishes_a_dangling_reference(tmp_path, monkeypatch, variant):
    from resume_api import rich_assets
    from resume_api.gui_projects import ProjectFailure
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    refs(service, fixture.project, 1)
    before = fixture.current()
    entered, release = threading.Event(), threading.Event()
    normalize = rich_assets.normalize_image
    def delayed(*args):
        entered.set()
        assert release.wait(10)
        return normalize(*args)
    monkeypatch.setattr(rich_assets, "normalize_image", delayed)
    task = asyncio.create_task(service.ingest_image(fixture.project, png(), capture()))
    assert await asyncio.to_thread(entered.wait, 10)
    if variant == "NB-A02:v01":
        refs(service, fixture.project, 2)
    elif variant == "NB-A02:v02":
        async def stop(project):
            fixture.jobs.mark_deleted(project)
        service.background_jobs.stop_project = stop
        assert (await service.delete_project(fixture.project)).status == "deleted"
    else:
        def fail(name, _project):
            if name == "before_workspace_replaced":
                raise OSError("Synthetic failure after actual image staging")
        fixture.coordinator.observer = fail
    release.set()
    with pytest.raises(ProjectFailure, match="PROJECT_SAVE_FAILED" if variant == "NB-A02:v03" else "STALE_IMAGE_INSERTION"):
        await task
    assert not service.image_reservations and not service.image_tasks
    if variant == "NB-A02:v02":
        assert not (fixture.canonical.projects / fixture.project).exists()
    else:
        assert fixture.current().project.document == before.project.document and not fixture.current().project.assets
        paths = list((fixture.canonical.projects / fixture.project / "images").glob("*"))
        assert bool(paths) == (variant == "NB-A02:v03")
        if paths:
            assert fixture.jobs.load(fixture.project).manual_intents[-1].phase == "fenced"
            assert fixture.fresh().coordinator.recover(fixture.project).manual_intents[-1].phase == "reconciled"
