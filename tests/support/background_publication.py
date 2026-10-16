"""Durable accepted inputs for the real canonical coordinator, without inference."""

import hashlib

from packages.resume_core.agent_artifacts import JobArtifacts
from packages.resume_core.agent_store import digest, journal_request
from packages.resume_core.background_history import ScopeHistory
from packages.resume_core.background_publication import CanonicalCoordinator
from packages.resume_core.background_scopes import mutation_selectors
from packages.resume_core.background_store import JobStore, expiration, job_in
from packages.resume_core.models.agent import AgentBatchJournal, AgentEditBatch, AgentQuery
from packages.resume_core.models.background import JobIdentity, ProposalBindingV1, ScopeGuardV1, WriterSessionV1
from packages.resume_core.project_store import encoded
from packages.resume_core.rich_mutations import mutation_sha256
from packages.resume_core.rich_project_store import RichProjectStore
from spikes.background.fixtures import TIME
from tests.recovery.test_background_inverse import mutation, put
from tests.recovery.test_background_store import capture
from tests.support.agent import isolated_project, run_request


class PublicationFixture:
    def __init__(self, root, *, create=True, observer=lambda _name, _project: None, validate=None):
        from resume_api.agent.context import canonical_capture, query_fingerprint
        self.root, self.capture = root, canonical_capture
        if create:
            _old, _canonical, self.initial, self.conversation = isolated_project(root)
        self.jobs = JobStore(root, clock=lambda: TIME)
        self.artifacts = JobArtifacts(self.jobs)
        self.canonical = RichProjectStore(root)
        self.originals, self.artifact_bytes, self.images = {}, {}, {}
        self.history = ScopeHistory(self.jobs, query_fingerprint)
        self.coordinator = CanonicalCoordinator(self.jobs, self.history, self.canonical, self.artifacts.payload_unlocked,
            observer=observer, **({"validate": validate} if validate else {}))
        if create:
            self.project = self.initial.project_id
            self.jobs.open(self.project)
            self.history.open(self.project)
            with self.jobs.guard(self.project) as directory:
                state = self.jobs._read(self.project, directory)
                state.writer = WriterSessionV1(schemaVersion=1, projectId=self.project, lineage=state.lineage,
                    epoch=1, sessionId="session", incarnation="instance", resumeCredentialSha256="a" * 64,
                    leaseExpiresAt=expiration(TIME, 15), status="clean_detached", acknowledgedRevision=1,
                    acknowledgedCursor=0, touchGeneration=0, barrierGeneration=0, draftId=None)
                self.jobs._write(directory, state, self.jobs._all())

    def current(self):
        return self.canonical.read_committed(self.project)[0]

    def accepted(self, key="one", *, queries=None, steps=None):
        workspace = self.current()
        queries = queries if queries is not None else [AgentQuery(kind="document", ids=["narrative"])]
        reads, dependencies = {}, []
        for query in queries:
            def read(current):
                value = self.capture(current, query)
                return value, value.dependencies
            captured, guards = self.history.observe(self.project, read)
            dependencies += captured.dependencies
            reads.update({stamp.key: stamp for stamp in guards.reads})
        context = self.jobs.load(self.project)
        request = journal_request(run_request(self.conversation.id, clientRequestId=key))
        identity = JobIdentity(projectId=self.project, lineage=context.lineage,
            requestEpoch=context.active_request_epoch, requestId=key)
        record = self.artifacts.prepare_input(identity, request, "account-one", digest(workspace.rules_used))
        submission = capture(context, key, input={"kind": "agent_journal", "id": record.id, "sha256": record.request_sha256},
            guards={"schemaVersion": 1, "reads": [], "writes": []})
        job, _created = self.jobs.submit(submission)
        self.artifacts.bind(job)
        original = mutation(workspace, steps or [put(workspace, "narrative")], "agent_" + key)
        original.capture.dependencies = list({(item.stamp.kind, item.stamp.id): item.stamp
            for item in dependencies if item.kind == "entity"}.values())
        batch = AgentEditBatch(id="batch_" + key, runId=job.id, toolKey="tool_" + key, ownerEpoch=1,
            state="prepared", scope=submission.scope, readSnapshotIds=[], dependencies=dependencies, mutation=original,
            requestSha256=mutation_sha256(original), previewSha256=digest([step.model_dump(mode="json", by_alias=True)
                for step in original.steps]), affected=[], factRecordIds=[])
        with self.jobs.guard(self.project) as directory:
            state = self.jobs._read(self.project, directory)
            writes = self.history.register(state, workspace, mutation_selectors(workspace, original), write=True)
            guard = ScopeGuardV1(schemaVersion=1, reads=list(reads.values()), writes=writes.writes)
            record = self.artifacts._artifact(self.artifacts._path(directory, job.submission.input.id))
            record.observed_guards, record.prepared_guards = guard, guard
            record.batches.append(AgentBatchJournal(key=batch.tool_key, payloadSha256=digest(key),
                result={"disposition": "prepared", "batchId": batch.id, "affected": [], "preview": "Synthetic edit"},
                batch=batch, receipt=None))
            self.artifacts._save(directory, state, record)
            raw = encoded(batch.model_dump(mode="json", by_alias=True))
            proposal = ProposalBindingV1(schemaVersion=1, id="proposal_" + key, jobId=job.id, projectId=self.project,
                lineage=state.lineage, accountGeneration=state.account_generation, executionGeneration=1,
                turnId="turn_" + key, payload={"kind": "agent_journal", "conversationId": self.conversation.id,
                    "runId": job.id, "batchId": batch.id}, payloadSha256=hashlib.sha256(raw).hexdigest(), payloadBytes=len(raw),
                guards=guard, scope=submission.scope, acceptedAt=TIME, executionDeadline=expiration(TIME, 180),
                authority="active", revocation=None)
            state.proposals.append(proposal)
            job = job_in(state, job.id)
            job.proposal_id, job.publication, job.execution = proposal.id, "waiting_for_sync", "completed"
            self.jobs._write(directory, state, self.jobs._all())
        return job, proposal, batch

    def publish(self, job, proposal):
        return self.coordinator.publish(self.project, job.id, proposal.payload_sha256,
            originals=self.originals, artifacts=self.artifact_bytes, images=self.images)

    def edit(self, identifier="quote", text="Independent input", key="manual"):
        before = self.current()
        return self.coordinator.manual(self.project, mutation(before, [put(before, identifier, text=text)], key),
            originals=self.originals, artifacts=self.artifact_bytes, images=self.images)[0]

    def snapshot(self, change, key="snapshot"):
        from packages.resume_core.background_history import digest_bytes
        before = self.current()
        after = before.model_copy(deep=True)
        change(after)
        after.project_revision += 1
        after.project.revision = after.project_revision
        after.project.document.revision = after.document_revision
        return self.coordinator.snapshot(self.project, digest_bytes(before), after, key,
            originals=self.originals, artifacts=self.artifact_bytes, images=self.images)[0]

    def fresh(self, **kwargs):
        value = PublicationFixture(self.root, create=False, **kwargs)
        value.project, value.initial, value.conversation = self.project, self.initial, self.conversation
        loaded, errors, _registry = value.canonical.load_all()
        assert not errors
        _workspace, value.originals, value.artifact_bytes, value.images = loaded[self.project]
        return value
