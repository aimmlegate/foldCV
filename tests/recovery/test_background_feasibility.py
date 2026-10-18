"""Reject stale transport reuse while preserving the original native snapshot."""

import copy
import json
from pathlib import Path
import subprocess

import pytest

from resume_api.jobs import feasibility


@pytest.fixture(scope="session")
def retained_transport_sources():
    # Load Git objects before the per-test synthetic child fence.
    root = Path.cwd()
    proof = json.loads((root / feasibility.PROOF).read_bytes())
    return {path: subprocess.check_output(["git", "show", f"{proof['executedRevision']}:{path}"], cwd=root)
        for path in feasibility.CRITICAL_SOURCES}


@pytest.fixture
def accepted_copy(tmp_path, monkeypatch, retained_transport_sources):
    root = Path.cwd()
    files = (feasibility.PROOF, feasibility.ACCEPTANCE, feasibility.MANIFEST, feasibility.VALIDATION)
    cache = {(feasibility.MILESTONE, path): (root / path).read_bytes() for path in files}
    proof = json.loads(cache[(feasibility.MILESTONE, feasibility.PROOF)])
    for path in feasibility.CRITICAL_SOURCES:
        cache[(proof["executedRevision"], path)] = retained_transport_sources[path]
    for (_revision, path), raw in cache.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    monkeypatch.setattr(feasibility, "ARTIFACT_PINS", dict(feasibility.ARTIFACT_PINS))
    binding = dict(evidence=feasibility.PROOF, pool="NB00", acceptedFeasibility=True,
        acceptedRevision=feasibility.MILESTONE)
    current = dict(proof["sourceHashes"])
    current["services/api/src/resume_api/app.py"] = "f" * 64
    return tmp_path, binding, proof, current, cache


def test_native_feasibility_can_apply_to_later_integration_without_restamping(accepted_copy):
    root, binding, proof, current, _cache = accepted_copy
    before = copy.deepcopy(proof)
    assert proof["sourceHashes"] != current
    assert feasibility.applicable(binding, proof, current, root)
    assert proof == before


@pytest.mark.parametrize("path", feasibility.CRITICAL_SOURCES)
def test_any_changed_transport_dependency_invalidates_native_feasibility(accepted_copy, path):
    root, binding, proof, current, _cache = accepted_copy
    target = root / path
    target.write_bytes(target.read_bytes() + b"\n# Synthetic changed transport.\n")
    with pytest.raises(ValueError, match="Native transport source changed"):
        feasibility.applicable(binding, proof, current, root)


@pytest.mark.parametrize("fault", ["revision", "pool", "evidence", "missing-opt-in", "changed-proof",
    "changed-acceptance", "changed-validation", "changed-manifest", "restamp", "current-hash", "no-go"])
def test_applicability_rejects_changed_or_unaccepted_provenance(accepted_copy, fault):
    root, binding, proof, current, cache = accepted_copy
    if fault == "revision": binding["acceptedRevision"] = "a" * 40
    elif fault == "pool": binding["pool"] = "NB07b"
    elif fault == "evidence": binding["evidence"] = "another-native-proof.json"
    elif fault == "missing-opt-in": binding.pop("acceptedFeasibility")
    elif fault in {"changed-proof", "changed-acceptance", "changed-validation", "changed-manifest"}:
        path = {"changed-proof": feasibility.PROOF, "changed-acceptance": feasibility.ACCEPTANCE,
            "changed-validation": feasibility.VALIDATION, "changed-manifest": feasibility.MANIFEST}[fault]
        (root / path).write_bytes((root / path).read_bytes() + b"\n")
    elif fault == "restamp": proof["sourceHashes"] = current
    elif fault == "current-hash": current[feasibility.CRITICAL_SOURCES[0]] = "e" * 64
    elif fault == "no-go":
        acceptance = json.loads((root / feasibility.ACCEPTANCE).read_bytes())
        acceptance["nativeGo"] = False
        raw = json.dumps(acceptance).encode()
        (root / feasibility.ACCEPTANCE).write_bytes(raw)
        cache[(feasibility.MILESTONE, feasibility.ACCEPTANCE)] = raw
        feasibility.ARTIFACT_PINS[feasibility.ACCEPTANCE] = feasibility.sha(raw)
    if fault in {"revision", "pool", "evidence", "missing-opt-in"}:
        assert not feasibility.applicable(binding, proof, current, root)
    else:
        with pytest.raises(ValueError):
            feasibility.applicable(binding, proof, current, root)


@pytest.mark.parametrize("fault", ["missing-authority", "injected-server", "disabled-background"])
def test_native_parallel_configuration_fails_before_profile_access(tmp_path, fault):
    from unittest.mock import Mock
    from resume_api.app import create_app
    profile = Mock()
    arguments = dict(origin="http://127.0.0.1:39288", secret="synthetic_parallel_secret_0123456789",
        temp_root=tmp_path / "operations", dist=tmp_path / "dist", experimental_profile=profile,
        background_enabled=fault != "disabled-background", background_parallel=True)
    if fault == "injected-server":
        arguments["background_server_factory"] = Mock()
    with pytest.raises(ValueError):
        create_app(**arguments)
    profile.prepare.assert_not_called()
    assert not arguments["temp_root"].exists()
