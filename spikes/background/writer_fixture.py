"""Retain exact compiler/store proof for browser writer checks."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.resume_core.models.background import WriterBarrierAckV1
from tests.recovery.test_background_history_commands import command, edit
from tests.recovery.test_background_history_transfer import transfer_request
from tests.recovery.test_background_writer_sessions import WriterFixture


def build(root):
    fixture = WriterFixture(root)
    job, proposal, _batch = fixture.publication.accepted()
    before = fixture.writers.flush(fixture.project, fixture.flush_request())
    barrier = fixture.writers.barrier(fixture.project, WriterBarrierAckV1(**fixture.flush_request().model_dump(by_alias=True),
        generation=before.writer.barrier_generation + 1, token="synthetic_barrier_token_012345678901234",
        touchGeneration=before.writer.touch_generation))
    saved = fixture.publication.publish(job, proposal)
    published = fixture.writers.read_snapshot(fixture.project, fixture.proof)
    request = transfer_request(fixture, job, proposal)
    offer = fixture.writers.history_offer(fixture.project, request)
    prepared = fixture.writers.begin_history_transfer(fixture.project, request)
    owner = fixture.writers.acknowledge_history_transfer(fixture.project, request)
    owned = fixture.writers.read_snapshot(fixture.project, fixture.proof)
    undone = fixture.writers.history_command(fixture.project, command(fixture, job, proposal))
    redone = fixture.writers.history_command(fixture.project, command(fixture, job, proposal, "redo", "redo-fixture"))
    edit(fixture, "quote", "Independent newer canonical input", "fixture-newer-input")
    newer_offer = fixture.writers.history_offer(fixture.project, transfer_request(fixture, job, proposal))
    return {key: value.model_dump(mode="json", by_alias=True) for key, value in dict(proof=fixture.proof,
        before=before, job=job, proposal=proposal, barrier=barrier, saved=saved, published=published,
        offer=offer, prepared=prepared, owner=owner, owned=owned, undone=undone, redone=redone, newerOffer=newer_offer).items()}


def controls(root, bridge):
    from packages.resume_core.models.background import BACKGROUND_CONTRACTS
    from tests.recovery.test_background_writer_drafts import checkpoint
    fixture = WriterFixture(root)
    request = checkpoint(fixture)
    draft = fixture.writers.checkpoint(fixture.project, request)
    reference = dict(schemaVersion=1, proof=fixture.proof.model_dump(by_alias=True), id=draft.id)
    command = {**reference, "sequence": draft.sequence, "payloadSha256": draft.payload_sha256,
        "canonicalRevision": fixture.view.workspace.project_revision, "canonicalSha256": fixture.view.workspace_sha256}
    header = fixture.flush_request().model_dump(by_alias=True)
    history = {**header, "jobId": bridge["job"]["id"], "proposalId": bridge["proposal"]["id"],
        "transferId": bridge["owner"]["transferId"]}
    barrier = {"schemaVersion": 1, "proof": reference["proof"], "generation": 1,
        "token": "synthetic_barrier_token_012345678901234"}
    examples = {
        "proof": reference["proof"], "open": fixture.open_request.model_dump(by_alias=True), "advance": header,
        "barrier_ack": {**header, **barrier, "touchGeneration": 0}, "barrier_command": barrier,
        "checkpoint": request.model_dump(by_alias=True),
        "abandon": {"schemaVersion": 1, "sessionId": "new-session", "incarnation": "new-connection",
            "credential": fixture.proof.credential, "canonicalRevision": fixture.view.workspace.project_revision,
            "canonicalSha256": fixture.view.workspace_sha256, "discardDrafts": []},
        "view": bridge["before"], "mutation": {**header, "mutation": request.payload.outbox[0].model_dump(by_alias=True)},
        "publish": {**barrier, "jobId": bridge["job"]["id"], "proposalSha256": bridge["proposal"]["payloadSha256"]},
        "publication": {"schemaVersion": 1, "job": bridge["saved"], "view": bridge["published"]},
        "history_request": history, "history_offer": bridge["offer"],
        "history_command": {**history, "commandId": "history-command", "direction": "undo"},
        "history_result": bridge["undone"], "draft_reference": reference, "draft_command": command,
        "draft_read": {"schemaVersion": 1, "checkpoint": draft.model_dump(by_alias=True), "payload": request.payload.model_dump(by_alias=True)},
        "draft_resolve": {**command, "mutation": request.payload.outbox[0].model_dump(by_alias=True)},
    }
    return {"background_writer_" + key + "_v1": BACKGROUND_CONTRACTS["background_writer_" + key + "_v1"].model_validate(value).model_dump(mode="json", by_alias=True)
        for key, value in examples.items()}


if __name__ == "__main__":
    import sys
    with TemporaryDirectory(prefix="foldcv-nb03-writer-fixture-", dir="/private/tmp") as root:
        result = build(Path(root))
        examples = controls(Path(root) / "controls", result)
    target = Path(sys.argv[1])
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if "--controls" in sys.argv:
        for name, value in examples.items():
            (target.parent / (name + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
