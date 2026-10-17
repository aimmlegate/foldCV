"""Retain native feasibility at its commit without restamping later builds."""

import hashlib
import json
from pathlib import Path


MILESTONE = "9938f54c67f8e593f914b18a5f8d156cba737b62"
HANDOFF = "docs/gui/handoffs/BACKGROUND-WORK/"
PROOF = HANDOFF + "nb00b-feasibility-native.json"
ACCEPTANCE = HANDOFF + "nb00b-acceptance.json"
MANIFEST = HANDOFF + "nb00b-source-manifest.json"
VALIDATION = HANDOFF + "nb00b-native-validation.json"
ARTIFACT_PINS = {
    PROOF: "83284ec55777663961fec6668a797503c65be93af2b5dac47143deca5ef18426",
    ACCEPTANCE: "39ffd00c890311e2e477e6f5f036c7b3fafa6304572d9082cc7eda483f720d41",
    MANIFEST: "5d615be84fbe11bcdf930690fc67ecf7d66f0a8c823c8adcd7e0558462765d90",
    VALIDATION: "142e4830b6a542fbf45e3c63370f97c790703d62cfbb744f0fb6ca3bbcae54c4",
}
SUPPORTING_PINS = {
    "spikes/agent/profile.py": "9ab49185cd773ac0ffda44a35aeb69144b80fb2894d81ab08893cecba5893734",
    "spikes/cli/profile.py": "6adf42bdb15bfeb6a1b2a2cd91bb31a0c7ef05ec009297294662dd08734d4234",
    "spikes/cli/runner.py": "8ef58fbe57b0721a57956a7a2eebc5176f174c5bf5298aabac69f60b42a92b8b",
}
CRITICAL_SOURCES = (
    "spikes/background/appserver_driver.py", "spikes/background/appserver_offline.py",
    "spikes/background/appserver_protocol.py", "spikes/background/appserver_schema.py",
    "spikes/background/appserver_wire.py", "services/api/src/resume_api/jobs/appserver.py",
    "services/api/src/resume_api/cli/experimental_profile.py", "services/api/src/resume_api/profile_ownership.py",
    "services/api/src/resume_api/lifecycle.py", "services/api/src/resume_api/agent/runtime.py",
    "services/api/src/resume_api/providers/codex_cli.py", "services/api/src/resume_api/providers/structured_schema.py",
    "spikes/agent/profile.py", "spikes/cli/profile.py", "spikes/cli/runner.py",
    "packages/resume_core/agent_limits.py", "packages/resume_core/background_limits.py",
    "packages/resume_core/models/agent.py", "packages/resume_core/models/background.py",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def accepted_transport(root):
    root = Path(root)
    records = {}
    for path in (PROOF, ACCEPTANCE, MANIFEST, VALIDATION):
        raw = (root / path).read_bytes()
        if sha(raw) != ARTIFACT_PINS[path]:
            raise ValueError("Accepted native evidence changed")
        records[path] = json.loads(raw)
    proof, acceptance, manifest, validation = (records[path] for path in (PROOF, ACCEPTANCE, MANIFEST, VALIDATION))
    if (acceptance["accepted"] is not True or acceptance["nativeGo"] is not True
            or acceptance["status"] != "accepted_with_review_debt" or validation["status"] != "passed"
            or validation["nativeGo"] is not True or proof["status"] != "accepted_with_review_debt"
            or acceptance["proof"] != PROOF or acceptance["validation"] != VALIDATION
            or proof["executedRevision"] != acceptance["baseRevision"]
            or set(proof["variants"]) != {"NB-R05:v01", "NB-R05:v02", "NB-R05:v03", "NB-R05:v04"}):
        raise ValueError("Missing accepted native transport")
    for path in (PROOF, ACCEPTANCE, VALIDATION):
        if sha((root / path).read_bytes()) != manifest["files"][path]:
            raise ValueError("Native acceptance manifest mismatch")
    sources = proof["sourceHashes"]
    encoded = json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()
    if sha(encoded) != validation["executedSourceSha256"]:
        raise ValueError("Native source snapshot changed")
    critical = {}
    for path in CRITICAL_SOURCES:
        expected = sources.get(path)
        if expected is None:
            expected = SUPPORTING_PINS[path]
        if sha((root / path).read_bytes()) != expected:
            raise ValueError("Native transport source changed: " + path)
        critical[path] = expected
    return proof, critical


def applicable(binding, report, sources, root):
    if (binding.get("acceptedRevision") != MILESTONE or binding.get("evidence") != PROOF
            or binding.get("pool") != "NB00" or binding.get("acceptedFeasibility") is not True):
        return False
    accepted, critical = accepted_transport(root)
    if report != accepted or any(path in sources and sources[path] != expected for path, expected in critical.items()):
        raise ValueError("Native feasibility does not apply to this source")
    return True


def require_native_transport(root):
    from tools.background_evidence import assert_native_bindings
    from spikes.background.native_turn_budget import ROLES
    proof, critical = accepted_transport(root)
    bindings = {variant: dict(evidence=PROOF, pool="NB00", transport="shared_appserver_v1", roles=ROLES[variant],
        **({"states": {"agent-A": "cancelled"}} if variant == "NB-R05:v01" else {})) for variant in proof["variants"]}
    assert_native_bindings(bindings, set(bindings), Path(root), sources=proof["sourceHashes"], require_pass=True)
    return critical
