"""Use the origin's existing journal for later UI receipts, including queued work."""

from packages.resume_core.agent_store import AgentFailure, run_in
from packages.resume_core.background_store import BackgroundFailure

from .publication import AgentPublication


class JournalService:
    def __init__(self, service, store):
        self.service, self.store = service, store

    def __getattr__(self, name):
        return getattr(self.service, name)


def origin_journal(service, value):
    project, origin = value.proposal.project_id, value.proposal.origin_run_id
    return journal_for_run(service, project, origin)


def journal_for_run(service, project, origin):
    try:
        run_in(service.store.load(project), origin)
        return service.store
    except AgentFailure as error:
        if error.code != "AGENT_NOT_FOUND":
            raise
    jobs = getattr(service.projects, "background_jobs", None)
    if jobs is None:
        raise AgentFailure("AGENT_NOT_FOUND")
    journal = jobs.artifacts.bound(project, origin)
    try:
        run_in(journal.load(project), origin)
    except BackgroundFailure as error:
        if error.code == "JOB_NOT_FOUND":
            raise AgentFailure("AGENT_NOT_FOUND") from None
        raise
    return journal


def origin_publication(service, value):
    store = origin_journal(service, value)
    return service.publication if store is service.store else AgentPublication(JournalService(service, store))


def known_application(service, project, key):
    state = service.store.load(project)
    found = [item for journal in state.journals for item in journal.batches if item.key == key]
    if len(found) == 1:
        return found[0]
    jobs = getattr(service.projects, "background_jobs", None)
    if jobs is not None and jobs.enabled:
        for job in jobs.store.load(project).jobs:
            if job.submission.kind != "agent":
                continue
            path = jobs.artifacts._path(jobs.store.projects / project, job.submission.input.id)
            if not path.exists():
                continue
            _job, artifact = jobs.artifacts.record(project, job.id)
            found.extend(item for item in getattr(artifact, "applications", []) if item.key == key)
    if len(found) > 1:
        raise AgentFailure("AGENT_OUTCOME_UNKNOWN")
    return found[0] if found else None
