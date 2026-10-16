"""Required regressions fail against disposable copies with a critical guard removed."""

import hashlib
import importlib.util
from pathlib import Path

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
