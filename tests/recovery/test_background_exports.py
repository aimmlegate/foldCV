"""One acknowledged export snapshot survives unrelated later canonical saves."""

import asyncio
import json

import pytest

from packages.resume_core.models.rich_document import ImageBlock
from packages.resume_core.project_store import encoded
from packages.resume_core.rich_mutations import locate
from tests.recovery.test_background_assets import image_fixture
from tests.recovery.test_background_conflicts import apply, record_step
from tests.recovery.test_background_inverse import mutation
from tests.recovery.test_background_writers import projects_for
from tests.recovery.test_rich_images_service import capture, png, refs
from tests.support.background_publication import PublicationFixture


class HeldRenderer:
    def __init__(self):
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.both_entered = asyncio.Event()
        self.calls = 0
        self.captured = None

    async def render(self, document, images, _files, facts):
        self.calls += 1
        if self.calls == 2:
            self.both_entered.set()
        self.captured = {"document": document.model_dump(mode="json", by_alias=True),
            "facts": facts.model_dump(mode="json", by_alias=True), "images": {key: value.hex() for key, value in images.items()}}
        self.entered.set()
        await self.release.wait()
        return encoded(self.captured)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [f"NB-A03:v{index:02d}" for index in range(1, 7)])
async def test_export_uses_revision_n_and_merges_only_its_later_metadata(tmp_path, variant):
    from resume_api.gui_projects import ProjectFailure
    if variant == "NB-A03:v06":
        fixture, service, _clock, aid, _path = await image_fixture(tmp_path)
        asset = fixture.current().project.assets[0]
        image = ImageBlock(id="export-image", revision=1, type="image", content=None, children=[], provenance=[],
            props={"assetId": aid, "alt": "Synthetic photo", "caption": [], "width": asset.width,
                "height": asset.height, "alignment": "left"})
        apply(fixture, [{"kind": "put_block", "block": image, "parentId": "job-section", "afterId": None,
            "beforeRevision": None}], "seed-image")
        assert service.persist(fixture.project) == "durable"
    else:
        fixture = PublicationFixture(tmp_path)
        service = projects_for(fixture, tmp_path)
    renderer = HeldRenderer()
    service.renderer = renderer
    captured = fixture.current()
    task = asyncio.create_task(service.export(fixture.project))
    await asyncio.wait_for(renderer.entered.wait(), 10)
    delete, other, other_task = None, None, None
    if variant == "NB-A03:v03":
        async def stop(project):
            fixture.jobs.mark_deleted(project)
        service.background_jobs.stop_project = stop
        key = next(key for key in service.tasks if key[0] == fixture.project)
        cancel = service.cancels[key]
        delete = asyncio.create_task(service.delete_project(fixture.project))
        assert await asyncio.to_thread(cancel.wait, 10)
    elif variant == "NB-A03:v04":
        other = fixture.current().model_copy(deep=True)
        other.project_id = other.project.project_id = "another-project"
        service.storage.save(other, {}, {})
        service.workspaces[other.project_id] = other
        service.saved_baselines[other.project_id] = other.model_copy(deep=True)
        other_task = asyncio.create_task(service.export(other.project_id))
        # The two calls may render together; neither holds the canonical lifecycle guard.
        await asyncio.wait_for(renderer.both_entered.wait(), 10)
        fixture.edit("quote", "Input while both projects render")
    elif variant == "NB-A03:v05":
        apply(fixture, [record_step(fixture.current(), "language-1")], "facts-after-capture")
    elif variant == "NB-A03:v06":
        refs(service, fixture.project, 3, (aid,), (aid,))
        replacement = await service.ingest_image(fixture.project, png("blue"), capture(3, "new-image"))
        before = fixture.current()
        located = locate(before.project.document, "export-image")
        changed = located[0][located[1]].model_copy(deep=True)
        changed.props.asset_id = replacement
        apply(fixture, [{"kind": "put_block", "block": changed, "beforeRevision": changed.revision,
            "parentId": "job-section", "afterId": None}],
            "image-after-capture")
        assert service.persist(fixture.project) == "durable"
        service.reclaim_images(fixture.project)
    else:
        fixture.edit("quote", "Text after export capture")
    latest = None if delete else fixture.current()
    renderer.release.set()
    if delete:
        with pytest.raises(ProjectFailure, match="STALE_EXPORT"):
            await task
        assert (await delete).status == "deleted"
        assert not service.artifacts and not service.images
    else:
        snapshot, blob = await task
        value = json.loads(blob)
        assert value["document"] == captured.project.document.model_dump(mode="json", by_alias=True)
        assert value["facts"] == captured.project.facts.model_dump(mode="json", by_alias=True)
        assert snapshot.document_revision == captured.document_revision and snapshot.facts_revision == captured.project.facts.revision
        assert fixture.current().project.document == latest.project.document and fixture.current().project.facts == latest.project.facts
        assert service.artifacts[(fixture.project, snapshot.id)] == blob
        cached = next(item for item in fixture.current().project.renders if item.id == snapshot.id)
        assert cached == snapshot and service.read(fixture.project) == fixture.current()
        if variant == "NB-A03:v06":
            assert value["images"][aid] == fixture.images[(fixture.project, aid)].hex()
            assert aid != replacement and replacement not in value["images"]
            saved_image = locate(fixture.current().project.document, "export-image")
            assert saved_image[0][saved_image[1]].props.asset_id == replacement
        if other_task:
            other_snapshot, _blob = await other_task
            assert other_snapshot.document_revision == other.document_revision
        assert not service.files and not service.tasks
        for project in (fixture.project, other.project_id if other else fixture.project):
            assert all(pin.kind != "export" for pin in fixture.jobs.load(project).asset_pins)
