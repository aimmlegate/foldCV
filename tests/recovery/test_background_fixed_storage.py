"""Fixed domain explanations and immutable payload ownership are independent of Saved."""

import hashlib
import json

import pytest

from packages.resume_core.background_fixed import fixed_mutation, fixed_payload
from packages.resume_core.background_scopes import mutation_selectors
from packages.resume_core.background_store import expiration, job_in
from packages.resume_core.models.agent import AgentEntityDependency
from packages.resume_core.models.background import ProposalBindingV1
from packages.resume_core.models.rich_workspace import RichSyncRecord
from packages.resume_core.rules import RulesStore
from tests.recovery.test_background_inverse import put
from tests.recovery.test_background_store import capture
from tests.recovery.test_background_writers import projects_for
from tests.support.background_publication import PublicationFixture


def accepted_fixed(fixture, *, conflict=False, empty=False, key="fixed-one"):
    service = projects_for(fixture, fixture.root)
    workspace = fixture.current()
    record = RichSyncRecord(id="sync_" + key, status="conflict" if conflict else "applied" if empty else "pending",
        actionId="action_" + key, blockIds=["narrative"], fieldKeys=["name"] if conflict else [], factIds=[],
        dependencies=[], errorCode="SEMANTIC_WARNING" if conflict else None, kind="rewrite", ready=not empty,
        proposedSteps=[] if empty else [put(workspace, "narrative", text="Fixed saved patch")], selection=None,
        instruction="Preserve a domain warning while applying a valid patch.")
    service.workspaces[fixture.project].sync_records.append(record)
    assert service.persist(fixture.project) == "durable"
    record = fixture.current().sync_records[-1]
    raw = fixed_payload(record)
    context = fixture.jobs.load(fixture.project)
    job, _created = fixture.jobs.submit(capture(context, key, kind="rewrite", schedulingClass="interactive",
        input={"kind": "rich_sync", "id": record.id, "sha256": hashlib.sha256(raw).hexdigest()},
        models=[{"stage": "rewrite", "model": "synthetic", "configSha256": "a" * 64}],
        tools=[], allowEdits=True, allowWeb=False))
    with fixture.jobs.guard(fixture.project) as directory:
        state = fixture.jobs._read(fixture.project, directory)
        workspace = fixture.canonical._read_committed_unlocked(fixture.project)[0]
        original = fixed_mutation(fixture.project, record)
        selectors = [AgentEntityDependency(kind="entity", stamp={"kind": "block", "id": "narrative",
            "revision": next(block.revision for block in workspace.project.document.blocks() if block.id == "narrative"),
            "fingerprint": None})]
        reads = fixture.history.register(state, workspace, selectors)
        writes = fixture.history.register(state, workspace, mutation_selectors(workspace, original), write=True) if original else reads
        proposal = ProposalBindingV1(schemaVersion=1, id="proposal_" + key, jobId=job.id, projectId=fixture.project,
            lineage=state.lineage, accountGeneration=state.account_generation, executionGeneration=1,
            turnId="turn_" + key, payload={"kind": "rich_sync", "syncId": record.id},
            payloadSha256=hashlib.sha256(raw).hexdigest(), payloadBytes=len(raw),
            guards={"schemaVersion": 1, "reads": reads.reads, "writes": writes.writes},
            scope=job.submission.scope, acceptedAt=fixture.jobs.clock(), executionDeadline=expiration(fixture.jobs.clock(), 180),
            authority="active", revocation=None)
        state.proposals.append(proposal)
        current = job_in(state, job.id)
        current.execution, current.publication, current.proposal_id = "completed", "waiting_for_sync", proposal.id
        fixture.jobs._write(directory, state, fixture.jobs._all())
    return service, job, proposal, record


@pytest.mark.parametrize("variant", ["NB-F04:v01", "NB-F04:v02", "NB-F04:v03"])
def test_fixed_domain_status_requires_exact_proof_and_keeps_one_original_payload(tmp_path, variant):
    from resume_api.gui_projects import ProjectFailure
    fixture = PublicationFixture(tmp_path)
    service, job, proposal, record = accepted_fixed(fixture, conflict=True, empty=variant == "NB-F04:v02")
    original = fixed_payload(record)
    before = fixture.current()
    if variant == "NB-F04:v03":
        with pytest.raises(ProjectFailure, match="JOB_SCOPE_INVALID"):
            service.disposition(fixture.project, record.id, "applied")
        assert fixture.current() == before
        assert fixture.jobs.read(fixture.project, job.id).receipt is None
        return
    result = fixture.publish(job, proposal)
    current = fixture.current()
    if variant == "NB-F04:v02":
        assert result.publication == "no_change" and result.receipt is None
        assert current == before and not fixture.jobs.load(fixture.project).intents
        assert fixture.publish(job, proposal) == result
    else:
        assert result.publication == "saved" and result.receipt.durable
        saved_record = current.sync_records[-1]
        assert saved_record.status == "conflict" and saved_record.error_code == "SEMANTIC_WARNING"
        assert not saved_record.ready and fixed_payload(saved_record) == original
        state = fixture.jobs.load(fixture.project)
        intent = state.intents[0]
        path = fixture.jobs.projects / fixture.project / "canonical-candidates" / (intent.candidate_ref + ".json")
        value = json.loads(path.read_bytes())
        assert not value["workspace"]["syncRecords"][-1]["proposedSteps"]
        assert value["syncPayloads"][0]["syncId"] == record.id
        assert "Fixed saved patch" not in json.dumps(value["workspace"]["syncRecords"])
        assert fixture.fresh().publish(job, proposal).receipt == result.receipt
        assert fixture.coordinator._load_candidate(state, path.parent.parent, intent).workspace == current


def test_generic_service_callback_cannot_change_an_accepted_fixed_payload(tmp_path):
    fixture = PublicationFixture(tmp_path)
    service, job, _proposal, record = accepted_fixed(fixture)
    cached = next(item for item in service.workspaces[fixture.project].sync_records if item.id == record.id)
    cached.proposed_steps.clear()
    assert service.persist(fixture.project) == "failed"
    assert service.save_errors[fixture.project] == "JOB_SCOPE_INVALID"
    assert fixture.current().sync_records[-1].proposed_steps
    assert fixture.jobs.read(fixture.project, job.id).receipt is None


@pytest.mark.parametrize("offset", [-1, 0, 1], ids=["below", "at", "above"])
def test_new_fixed_body_reaches_its_exact_byte_limit_before_canonical_write(tmp_path, offset):
    from packages.resume_core.background_limits import LIMITS
    fixture = PublicationFixture(tmp_path)
    service = projects_for(fixture, tmp_path)
    before = fixture.current()
    record = RichSyncRecord(id="bounded-fixed-body", status="pending", actionId="bounded-action",
        blockIds=["narrative"], fieldKeys=[], factIds=[], dependencies=[], errorCode=None,
        kind="rewrite", ready=True, proposedSteps=[put(before, "narrative")], instruction="")
    record.instruction = "x" * (LIMITS.proposal_bytes - len(fixed_payload(record)) + offset)
    assert len(fixed_payload(record)) == LIMITS.proposal_bytes + offset
    service.workspaces[fixture.project].sync_records.append(record)
    outcome = service.persist(fixture.project)
    if offset > 0:
        assert outcome == "failed" and service.save_errors[fixture.project] == "JOB_STORAGE_FULL"
        assert fixture.current() == before
    else:
        assert outcome == "durable" and fixed_payload(fixture.current().sync_records[-1]) == fixed_payload(record)
    assert not fixture.jobs.load(fixture.project).intents
