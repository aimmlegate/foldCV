"""Serialize private preparation; canonical publication is a separate editor gate."""

from pydantic import ValidationError

from packages.resume_core.agent_edits import compile_batch
from packages.resume_core.agent_store import AgentFailure, digest, run_in
from packages.resume_core.models.agent import AgentQuery, AgentQueryDependency
from packages.resume_core.rich_mutations import RichMutationFailure

from .context import query_fingerprint


def prepare(session, request):
    service, control = session.service, session.control
    with service.projects.state_lock:
        session.guard()
        _, _, journal = run_in(service.store.load(control.project_id), control.run_id)
        prior = next((item for item in journal.batches if item.key == request.key), None)
        if prior is not None:
            if prior.payload_sha256 != digest(request):
                raise AgentFailure("AGENT_IDEMPOTENCY_CONFLICT")
            return prior.result
        workspace = service.projects.read(control.project_id)
        if not session.book.validate(workspace):
            raise AgentFailure("AGENT_STALE_READ")
        writer_session_id = session.writer_session_id()
        def compile_command(state, run, journal):
            if state.owner_epoch != control.owner_epoch:
                raise AgentFailure("AGENT_OWNER_MISMATCH")
            result, batch = compile_batch(workspace, run, journal, request, session.book, writer_session_id)
            if batch is not None:
                ids = [identifier for identifier in batch.fact_record_ids if any(record.id == identifier for record in workspace.project.facts.records)]
                if ids:
                    query = AgentQuery(kind="facts", ids=ids, parentId="linked")
                    batch.dependencies.append(AgentQueryDependency(kind="query", query=query,
                        fingerprint=query_fingerprint(workspace, query)))
            return result, batch
        try:
            return service.store.prepare(control.project_id, control.run_id, request, compile_command)
        except AgentFailure:
            raise
        except (RichMutationFailure, ValidationError, ValueError, KeyError, AttributeError):
            raise AgentFailure("AGENT_EDIT_INVALID") from None
