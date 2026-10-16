"""History component checks; full publication variants require the NB02 coordinator."""

import json

import pytest

from packages.resume_core.background_history import ScopeHistory
from packages.resume_core.background_store import BackgroundFailure, JobStore
from packages.resume_core.models.agent import AgentEntityDependency, AgentQuery, AgentQueryDependency
from packages.resume_core.models.background import ScopeGuardV1
from packages.resume_core.project_store import encoded
from packages.resume_core.rich_dependencies import dependency
from packages.resume_core.rich_project_store import rich_snapshot_bytes
from packages.resume_core.storage import atomic_write
from spikes.background.fixtures import TIME
from tests.recovery.test_background_store import capture
from tests.support.agent import isolated_project


def environment(root, observer=lambda _name, _project: None):
    from resume_api.agent.context import query_fingerprint
    _, canonical, workspace, _ = isolated_project(root)
    jobs = JobStore(root, clock=lambda: TIME)
    jobs.open(workspace.project_id)
    history = ScopeHistory(jobs, query_fingerprint, observer=observer)
    return jobs, canonical, workspace, history


def read_block(workspace):
    selector = AgentEntityDependency(kind="entity", stamp=dependency(workspace, "block", "narrative"))
    return workspace, [selector]


def component_write(jobs, canonical, history, before, candidate, *, touches=frozenset()):
    prepared = canonical.prepare_save(candidate, {}, {})
    with jobs.guard(before.project_id) as directory:
        state = jobs._read(before.project_id, directory)
        def persist_history(_checksum):
            history.advance(state, before, candidate, touches=touches)
            jobs._write(directory, state, jobs._all())
        canonical._commit_prepared_unlocked(prepared, after_workspace=persist_history)


def edit(before, text):
    value = before.model_copy(deep=True)
    block = next(block for block in value.project.document.blocks() if block.id == "narrative")
    block.content[0].text = text
    block.revision += 1
    value.project_revision += 1
    value.document_revision += 1
    value.project.revision = value.project_revision
    value.project.document.revision = value.document_revision
    return value


def validate(jobs, canonical, history, project, guard):
    with jobs.guard(project) as directory:
        state = jobs._read(project, directory)
        current, _checksum = canonical._read_committed_unlocked(project)
        return history.validate(state, directory, current, guard)


def test_history_capture_and_aba_preserve_monotonic_scoped_generations(tmp_path):
    jobs, canonical, workspace, history = environment(tmp_path)
    first, guard = history.observe(workspace.project_id, read_block)
    assert validate(jobs, canonical, history, workspace.project_id, guard)
    changed = edit(first, "Changed synthetic text")
    component_write(jobs, canonical, history, first, changed)
    restored = first.model_copy(deep=True)
    restored.project_revision = changed.project_revision + 1
    restored.document_revision = changed.document_revision + 1
    restored.project.revision = restored.project_revision
    restored.project.document.revision = restored.document_revision
    component_write(jobs, canonical, history, changed, restored)
    with pytest.raises(BackgroundFailure, match="DEPENDENCY_CHANGED"):
        validate(jobs, canonical, history, workspace.project_id, guard)
    _value, current = history.observe(workspace.project_id, read_block)
    assert current.reads[-1].fingerprint == guard.reads[-1].fingerprint
    assert current.reads[-1].generation > guard.reads[-1].generation
    assert validate(jobs, canonical, history, workspace.project_id, current)
    combined = ScopeGuardV1(schemaVersion=1, reads=guard.reads, writes=current.reads)
    with pytest.raises(BackgroundFailure, match="DEPENDENCY_CHANGED"):
        validate(jobs, canonical, history, workspace.project_id, combined)


@pytest.mark.parametrize("boundary", ["history_initializing", "history_activation_durable"])
def test_partial_history_activation_recovers_the_same_namespace(tmp_path, boundary):
    reached = []
    def fail(name, project):
        if name == boundary:
            reached.append(project)
            raise OSError("synthetic history activation interruption")
    jobs, canonical, workspace, history = environment(tmp_path, fail)
    with pytest.raises(BackgroundFailure, match="JOB_STORE_UNAVAILABLE"):
        history.open(workspace.project_id)
    old = jobs.load(workspace.project_id).history
    assert old.phase == "initializing" and reached == [workspace.project_id]
    fresh = ScopeHistory(jobs, history.query_fingerprint)
    restored = fresh.open(workspace.project_id)
    assert restored.phase == "ready" and restored.namespace == old.namespace
    assert fresh.open(workspace.project_id) == restored
    assert canonical.read_committed(workspace.project_id)[0] == workspace


@pytest.mark.parametrize("fault", ["activation-missing", "metadata-missing", "outside-writer"])
def test_missing_activated_history_and_uncoordinated_writes_fence_without_reset(tmp_path, fault):
    jobs, canonical, workspace, history = environment(tmp_path)
    history.open(workspace.project_id)
    directory = jobs.projects / workspace.project_id
    if fault == "activation-missing":
        (directory / "history-activation.json").unlink()
    elif fault == "metadata-missing":
        value = json.loads((directory / "state.json").read_bytes())
        value["history"], value["generations"] = None, []
        atomic_write(directory / "state.json", encoded(value))
    else:
        atomic_write(canonical.projects / workspace.project_id / "workspace.json", rich_snapshot_bytes(edit(workspace, "Uncoordinated change")))
    before = (directory / "state.json").read_bytes()
    fresh = ScopeHistory(JobStore(tmp_path), history.query_fingerprint)
    with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
        fresh.open(workspace.project_id)
    assert (directory / "state.json").read_bytes() == before


def test_zero_diff_touch_invalidates_only_its_registered_scope(tmp_path):
    jobs, canonical, workspace, history = environment(tmp_path)
    _value, guard = history.observe(workspace.project_id, read_block)
    component_write(jobs, canonical, history, workspace, workspace, touches={guard.reads[-1].key})
    with pytest.raises(BackgroundFailure, match="DEPENDENCY_CHANGED"):
        validate(jobs, canonical, history, workspace.project_id, guard)
    _value, untouched = history.observe(workspace.project_id, read_block)
    component_write(jobs, canonical, history, workspace, workspace, touches={"another-scope"})
    assert validate(jobs, canonical, history, workspace.project_id, untouched)


def test_empty_query_aba_cannot_restore_an_old_guard(tmp_path):
    jobs, canonical, workspace, history = environment(tmp_path)
    query = AgentQuery(kind="find", text="NEW_SYNTHETIC_MATCH")
    def read(value):
        return value, [AgentQueryDependency(kind="query", query=query, fingerprint=history.query_fingerprint(value, query))]
    _value, guard = history.observe(workspace.project_id, read)
    changed = edit(workspace, "NEW_SYNTHETIC_MATCH")
    component_write(jobs, canonical, history, workspace, changed)
    restored = workspace.model_copy(deep=True)
    restored.project_revision, restored.document_revision = changed.project_revision + 1, changed.document_revision + 1
    restored.project.revision = restored.project_revision
    restored.project.document.revision = restored.document_revision
    component_write(jobs, canonical, history, changed, restored)
    with pytest.raises(BackgroundFailure, match="DEPENDENCY_CHANGED"):
        validate(jobs, canonical, history, workspace.project_id, guard)


def test_additive_private_fields_do_not_rewrite_an_old_exact_retry(tmp_path):
    jobs, _canonical, workspace, _history = environment(tmp_path)
    context = jobs.load(workspace.project_id)
    request = capture(context)
    job, _created = jobs.submit(request)
    path = jobs.projects / workspace.project_id / "state.json"
    value = json.loads(path.read_bytes())
    value.pop("history")
    old = encoded(value)
    atomic_write(path, old)
    replay, created = jobs.submit(request)
    assert not created and replay == job and path.read_bytes() == old
