"""Synthetic fixed replies and canonical fixtures for manual and cross-layer proof."""

import json

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.models.rich_document import FactFieldSpan, NarrativeCitation
from packages.resume_core.models.rich_mutations import RichSelection
from packages.resume_core.models.rich_workspace import RichSyncRecord
from packages.resume_core.rich_panel import RichPanelProposal
from packages.resume_core.rich_sync import scoped_dependencies, selection_parts, selection_checksum
from resume_api.providers.content import ContentResult, ReportedUsage
from tests.recovery.generation_fixtures import CreationProvider


class FixedProofProvider(CreationProvider):
    def generate(self, request, files, cancel):
        if request.result_type is RichPanelProposal:
            assert not request.policy.allow_repair
            payload = json.loads(request.text)
            self.calls.append(payload)
            value = RichPanelProposal(updates=[{"blockId": b["id"], "text": "Panel result for " + b["id"]}
                for b in payload["input"]["blocks"]])
            return ContentResult(value, ReportedUsage(), "scripted", request.policy.model, 0, 1)
        return super().generate(request, files, cancel)


def prepare_fixed(bridge, project):
    service = bridge.service
    provider = getattr(bridge, "fixed_provider", None) or FixedProofProvider()
    bridge.fixed_provider = provider
    service.projects.provider_factory = lambda: (provider, "processing-model")
    before, checksum = service.projects.storage.read_committed(project)
    after = before.model_copy(deep=True)
    after.sync_records = [s for s in after.sync_records if not s.id.startswith("legacy-")]
    blocks = {b.id: b for b in after.project.document.blocks()}
    blocks["title"].content[0].text = "Senior Engineer"
    blocks["language"].content = [FactFieldSpan(type="fact_field", bindingId="fixed-level-binding",
        bindingRootId="fixed-level-root", recordId="language-1", fieldKey="level", syncedFactRevision=1,
        text="Advanced", styles={})]
    for block, record in [("narrative", "candidate-1"), ("quote", "language-1")]:
        blocks[block].provenance = [NarrativeCitation(kind="citation", id="fixed-cite-" + block,
            recordId=record, fieldKeys=["title" if record == "candidate-1" else "level"], evidence=[])]
        selected = RichSelection(kind="text", anchor={"blockId": block, "cellId": None, "offset": 0},
            head={"blockId": block, "cellId": None, "offset": 6}, blockIds=[block],
            capture={"sessionId": "legacy", "actionId": "legacy-" + block, "actionToken": 0, "dependencies": []},
            textSha256="0" * 64)
        selected.text_sha256 = selection_checksum(selection_parts(after, selected))
        after.sync_records.append(RichSyncRecord(id="legacy-" + block, status="failed", actionId="legacy-" + block,
            blockIds=[block], fieldKeys=[], factIds=[record], dependencies=scoped_dependencies(after, [block], [record]),
            errorCode="MODEL_DENIED", kind="rewrite", ready=False, proposedSteps=[], selection=selected, instruction="Clarify"))
    service.writers.initialize(project)
    saved, _ = service.publisher.snapshot(project, checksum, after, "metadata_fixed_fixture",
        originals=service.projects.originals, artifacts=service.projects.artifacts, images=service.projects.images)
    service.publication.adopt(project, saved, digest_bytes(saved))
    return service.projects.response(project).model_dump(mode="json", by_alias=True)
