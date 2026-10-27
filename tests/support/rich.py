"""The synthetic rich workspace fixture and small builders for mutations, selections and completion requests."""

from io import BytesIO
import json
from pathlib import Path

from PIL import Image

from packages.resume_core.models.rich_document import ImageBlock
from packages.resume_core.models.rich_mutations import RichMutation, RichSelection
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.rendering.rich_template import require_rich_template
from packages.resume_core.rich_images import normalize_image
from packages.resume_core.rich_sync import RichCompletionRequest, selection_checksum, selection_parts

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/rich_workspace.json"


def fixture():
    return WorkspaceV6.model_validate(json.loads(FIXTURE.read_text()))


def without_sources():
    workspace = fixture()
    workspace.project.template = require_rich_template().manifest
    workspace.project.sources = []
    workspace.project.assets = []
    workspace.project.document.regions[2].blocks = [b for b in workspace.project.document.regions[2].blocks if b.type != "image"]
    return workspace


def image_asset(workspace):
    output = BytesIO()
    Image.new("RGB", (16, 8), "red").save(output, format="PNG")
    asset, blob = normalize_image(output.getvalue(), "asset-test")
    workspace.project.assets = [asset]
    workspace.project.document.regions[2].blocks.append(ImageBlock.model_validate({"type": "image", "id": "test-image",
        "revision": 1, "children": [], "provenance": [], "content": None, "props": {"assetId": asset.id,
            "alt": "red test", "caption": [], "width": 160.0, "height": 80.0, "alignment": "left"}}))
    return asset, blob


def patch(workspace, text="Changed", identifier="change-1"):
    block = workspace.project.document.regions[0].blocks[0].model_copy(deep=True)
    block.content[0].text = text
    return RichMutation.model_validate({"schemaVersion": 1, "projectId": workspace.project_id,
        "clientMutationId": identifier, "actionId": identifier, "kind": "typing",
        "capture": {"sessionId": "session", "actionId": identifier, "actionToken": 0, "dependencies": []},
        "steps": [{"kind": "put_block", "parentId": "header", "afterId": None,
            "beforeRevision": block.revision, "block": block.model_dump(by_alias=True)}]})


def capture(action="edit"):
    return {"sessionId": "session", "actionId": action, "actionToken": 0, "dependencies": []}


def completion(**values):
    return RichCompletionRequest.model_validate({"capture": capture(), "blockIds": ["title"], "movedIds": [], "removedFields": [],
        "interpret": False, **values})


def mutation(workspace, steps, stamps=(), id="apply"):
    return RichMutation.model_validate({"schemaVersion": 1, "projectId": workspace.project_id,
        "clientMutationId": id, "actionId": id, "kind": "reconciliation", "capture": {**capture(id), "dependencies": list(stamps)},
        "steps": steps})


def selection(workspace, id="narrative", start=0, end=6):
    value = RichSelection.model_validate({"kind": "text", "anchor": {"blockId": id, "cellId": None, "offset": start},
        "head": {"blockId": id, "cellId": None, "offset": end}, "blockIds": [id], "capture": capture(), "textSha256": "0" * 64})
    value.text_sha256 = selection_checksum(selection_parts(workspace, value))
    return value
