"""Required regressions fail against disposable copies with a critical guard removed."""

import hashlib
import importlib.util
from pathlib import Path
import asyncio

import pytest

from packages.resume_core.models.agent import AgentQuery
from packages.resume_core.rich_mutations import RichMutationFailure, apply_rich_mutation
from tests.recovery.test_background_inverse import mutation, put
from tests.recovery.test_background_publication_crashes import attach
from tests.support.background_publication import PublicationFixture


def copied_module(tmp_path, name, changes):
    source = Path("packages/resume_core") / (name + ".py")
    raw = source.read_text()
    altered = raw
    for before, after in changes:
        assert altered.count(before) == 1
        altered = altered.replace(before, after)
    path = tmp_path / (name + "_mutant.py")
    path.write_text(altered)
    spec = importlib.util.spec_from_file_location("packages.resume_core._" + name + "_guard_mutant", path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name)
    return module, hashlib.sha256(raw.encode()).hexdigest(), hashlib.sha256(altered.encode()).hexdigest()


@pytest.mark.parametrize("variant", ["NB-G03:v01", "NB-G03:v02", "NB-G03:v05"])
def test_critical_guard_omission_breaks_the_actual_regression(tmp_path, variant, background_evidence):
    healthy = PublicationFixture(tmp_path / "healthy")
    broken = PublicationFixture(tmp_path / "mutant")
    if variant == "NB-G03:v01":
        module, original_sha, mutant_sha = copied_module(tmp_path, "background_history", [
            ("captured = [*guards.reads, *guards.writes]", "captured = [*guards.writes]")])
        broken.history = broken.coordinator.history = module.ScopeHistory(broken.jobs, broken.history.query_fingerprint)
        results = []
        for fixture in (healthy, broken):
            fixture.edit("quote", "MATCH_TOKEN", "seed")
            job, proposal, _batch = fixture.accepted(queries=[AgentQuery(kind="find", text="MATCH_TOKEN")])
            fixture.edit("quote", "Changed membership", "change")
            results.append(fixture.publish(job, proposal).publication)
        assert results == ["needs_review", "saved"]
        with pytest.raises(AssertionError, match="read-dependency regression"):
            assert results[1] == "needs_review", "read-dependency regression"
        failure = "read-dependency regression: saved instead of needs_review"
    elif variant == "NB-G03:v02":
        module, original_sha, mutant_sha = copied_module(tmp_path, "background_authority", [
            ("barrier.incarnation, barrier.generation, barrier.acknowledged_revision", "barrier.incarnation, barrier.acknowledged_revision"),
            ("writer.incarnation, writer.barrier_generation, workspace.project_revision", "writer.incarnation, workspace.project_revision")])
        broken.coordinator.authority = module.PublicationAuthority()
        results = []
        for fixture in (healthy, broken):
            job, proposal, _batch = fixture.accepted()
            attach(fixture)
            with fixture.jobs.guard(fixture.project) as directory:
                state = fixture.jobs._read(fixture.project, directory)
                state.writer.barrier_generation += 1
                fixture.jobs._write(directory, state, fixture.jobs._all())
            results.append(fixture.publish(job, proposal).publication)
        assert results == ["waiting_for_sync", "saved"]
        with pytest.raises(AssertionError, match="barrier-generation regression"):
            assert results[1] == "waiting_for_sync", "barrier-generation regression"
        failure = "barrier-generation regression: saved with an old barrier generation"
    else:
        module, original_sha, mutant_sha = copied_module(tmp_path, "rich_mutations", [
            ("    if replay:\n", "    if replay and False:\n")])
        request = mutation(healthy.current(), [put(healthy.current(), "narrative")], "same-request")
        saved, replayed = healthy.coordinator.manual(healthy.project, request)
        assert not replayed
        unchanged, replayed = apply_rich_mutation(saved, request)
        assert replayed and unchanged == saved
        with pytest.raises(module.RichMutationFailure, match="STALE_MUTATION"):
            module.apply_rich_mutation(saved, request)
        failure = "mutation-replay regression: STALE_MUTATION instead of an unchanged exact duplicate"
        results = ["unchanged_duplicate", "stale_new_application"]
    assert original_sha != mutant_sha
    background_evidence({"id": variant + ":sensitivity", "seed": 0, "capacity": 1, "transitions": 2,
        "actions": ["healthy", "mutant"], "orders": ["healthy_then_mutant"], "scope": "production_integration",
        "log": [{"action": "healthy", "result": results[0], "sourceSha256": original_sha},
            {"action": "mutant", "result": results[1], "sourceSha256": mutant_sha, "regressionFailure": failure}]})


def test_zero_diff_touch_guard_omission_breaks_the_scoped_aba_regression(tmp_path, background_evidence):
    from tests.recovery.test_background_writer_sessions import WriterFixture
    module, source_sha, mutant_sha = copied_module(tmp_path, "background_writers", [
        ("                touched.update(query_touches(state, workspace, workspace, item.mutation))",
         "                pass")])
    results = []
    for label in ("healthy", "mutant"):
        fixture = WriterFixture(tmp_path / label)
        if label == "mutant":
            original = fixture.writers
            fixture.writers = module.WriterSessions(fixture.publication.coordinator)
            fixture.writers.live = original.live
        job, proposal, _batch = fixture.publication.accepted()
        before = fixture.publication.current()
        edit = mutation(before, [put(before, "narrative", text="Typed and undone")], "zero-diff-touch")
        edit.capture.session_id = fixture.proof.session_id
        fixture.writers.flush(fixture.project, fixture.flush_request(1, [{"cursor": 1, "mutation": edit}]))
        assert fixture.publication.current() == before
        fixture.writers.detach(fixture.project, fixture.flush_request(1))
        results.append(fixture.publication.publish(job, proposal).publication)
    assert results == ["needs_review", "saved"]
    with pytest.raises(AssertionError, match="zero-diff regression"):
        assert results[1] == "needs_review", "zero-diff regression"
    background_evidence({"id": "NB-G03:v04:sensitivity", "seed": 0, "capacity": 1, "transitions": 2,
        "actions": ["healthy", "mutant"], "orders": ["healthy_then_mutant"], "scope": "production_integration",
        "log": [{"action": "healthy", "result": results[0], "sourceSha256": source_sha},
            {"action": "mutant", "result": results[1], "sourceSha256": mutant_sha,
                "regressionFailure": "zero-diff regression: saved after uncommitted edit and Undo"}]})


@pytest.mark.asyncio
async def test_releasing_a_slot_before_cleanup_fails_the_actual_ownership_invariant(tmp_path, background_evidence):
    from tests.recovery.test_background_supervisor import environment
    from tests.recovery.test_background_store import capture
    module, source_sha, mutant_sha = copied_module(tmp_path, "background_supervisor", [
        ("        control.revoked = True\n        close = asyncio.create_task(control.owned.close())",
         "        control.revoked = True\n        self.active = None\n        close = asyncio.create_task(control.owned.close())")])
    rows = []
    for label in ("healthy", "mutant"):
        store, state, clock, factory, supervisor = await environment(tmp_path / label)
        if label == "mutant":
            supervisor.__class__ = module.JobSupervisor
        factory.hold_cleanup.add("cleanup-owner")
        try:
            job, _ = await supervisor.submit(capture(state, "cleanup-owner"))
            actor = await factory.actor(job)
            await asyncio.wait_for(actor.cleanup_started.wait(), 10)
            control = supervisor.controls[job.id]
            assert actor.child.command("probe") == {"type": "alive"}
            def assert_owner():
                assert supervisor.active is control, "NB-I06: slot released before owned child cleanup"
            if label == "healthy":
                assert_owner()
            else:
                with pytest.raises(AssertionError, match="NB-I06: slot released before owned child cleanup"):
                    assert_owner()
            rows.append(dict(action=label, result="owned" if supervisor.active is control else "premature_release",
                sourceSha256=source_sha if label == "healthy" else mutant_sha,
                regressionFailure="none" if label == "healthy" else "NB-I06: slot released before owned child cleanup"))
            actor.cleanup_permission.set()
            await asyncio.wait_for(control.task, 10)
            assert store.read(state.project_id, job.id).attempts[-1].cleanup_verified
        finally:
            for actor in factory.actors.values():
                actor.cleanup_permission.set()
            await supervisor.shutdown()
            factory.verify(); clock.verify()
    background_evidence(dict(id="NB-G03:v06:sensitivity", seed=0, capacity=1, transitions=2,
        actions=["healthy", "mutant"], orders=["healthy_then_mutant"], scope="production_integration", log=rows))
