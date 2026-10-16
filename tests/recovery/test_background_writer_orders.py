"""Named authority and recovery schedules check each real persisted transition."""

from concurrent.futures import ThreadPoolExecutor
from itertools import permutations
import threading

import pytest

from packages.resume_core.background_history import digest_bytes
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.background_writers import WriterSessions
from packages.resume_core.models.background import WriterMutationV1
from tests.recovery.test_background_inverse import block, mutation, put
from tests.recovery.test_background_writer_sessions import WriterFixture
from tests.support.background_publication import PublicationFixture


@pytest.mark.parametrize("variant,first", [("NB-W10:v01", "attach"), ("NB-W10:v02", "commit")], ids=["NB-W10:v01", "NB-W10:v02"])
def test_attach_and_headless_commit_use_one_real_canonical_order(tmp_path, variant, first):
    fixture = WriterFixture(tmp_path)
    job, proposal, _batch = fixture.publication.accepted()
    fixture.writers.detach(fixture.project, fixture.flush_request())
    entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
    cut = "writer_resumed" if first == "attach" else "workspace_durable"
    def observe(name, _project):
        if name == cut:
            entered.set(); assert release.wait(10)
    fixture.writers.observer = fixture.publication.coordinator.observer = observe
    def attach():
        return fixture.writers.open(fixture.project, fixture.open_request.model_copy(update={"incarnation": "racing-attach"}))
    def commit():
        return fixture.publication.publish(job, proposal)
    operations = {"attach": attach, "commit": commit}
    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(operations[first])
        assert entered.wait(10)
        def later():
            attempted.set()
            return operations["commit" if first == "attach" else "attach"]()
        loser = pool.submit(later)
        try:
            assert attempted.wait(10)
        finally:
            release.set()
        values = {first: winner.result(timeout=10), "commit" if first == "attach" else "attach": loser.result(timeout=10)}
    result = values["commit"]
    assert result.publication == ("saved" if first == "commit" else "waiting_for_sync")
    assert len(fixture.publication.current().mutation_replay) == int(first == "commit")
    assert values["attach"].writer.status == "attached"
    assert values["attach"].workspace == fixture.publication.current()
    assert fixture.publication.jobs.load(fixture.project).writer.incarnation == "racing-attach"


ORDERS = list(permutations(("edit", "undo", "detach")))


@pytest.mark.parametrize("order", ORDERS, ids=lambda order: "-".join(order))
def test_edit_undo_detach_schedules_preserve_the_independent_input_oracle(tmp_path, order, background_evidence):
    fixture = WriterFixture(tmp_path)
    original = block(fixture.publication.current(), "quote").content[0].text
    expected, detached, edited, cursor, revision = original, False, False, 0, fixture.view.workspace.project_revision
    log = []
    for action in order:
        if action == "detach":
            fixture.writers.detach(fixture.project, fixture.flush_request(cursor)); detached = True; result = "detached"
        elif action == "undo" and not edited:
            assert fixture.writers.read_snapshot(fixture.project, fixture.proof).workspace == fixture.publication.current()
            result = "empty_history"
        else:
            text = original if action == "undo" else "Accepted local input"
            current = fixture.publication.current()
            change = mutation(current, [put(current, "quote", text=text)], action)
            change.kind, change.capture.session_id = "undo" if action == "undo" else "typing", fixture.proof.session_id
            request = WriterMutationV1(**fixture.flush_request(cursor + 1, [{"cursor": cursor + 1, "mutation": change}]).model_dump(by_alias=True), mutation=change)
            if detached:
                with pytest.raises(BackgroundFailure, match="WRITER_UNKNOWN"):
                    fixture.writers.save(fixture.project, request)
                result = "rejected"
            else:
                fixture.writers.save(fixture.project, request)
                cursor += 1; revision += 1; expected, edited = text, action == "edit"; result = "saved"
        current = fixture.publication.current()
        assert block(current, "quote").content[0].text == expected
        state = fixture.publication.jobs.load(fixture.project)
        assert current.project_revision == revision and state.writer.acknowledged_cursor == cursor
        assert state.writer.status == ("clean_detached" if detached else "attached")
        log.append(dict(action=action, project="A", job="one", result=result, revision=revision, cursor=cursor))
    background_evidence(dict(id="NB03:edit-order:" + "-".join(order), seed=0, capacity=1, transitions=3,
        actions=sorted({row["action"] for row in log if row["result"] != "rejected"}), orders=[], log=log, scope="production_integration"))


@pytest.mark.parametrize("order", list(permutations(("delete", "restart", "callback"))), ids=lambda order: "-".join(order))
def test_delete_restart_and_late_callback_schedules_never_resurrect_authority(tmp_path, order, background_evidence):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    deleted, committed = False, False
    log = []
    for action in order:
        if action == "delete":
            fixture.canonical.tombstone(fixture.project); fixture.jobs.mark_deleted(fixture.project)
            deleted = True; result = "tombstoned"
        elif action == "restart":
            fresh = PublicationFixture(tmp_path, create=False)
            fresh.project, fresh.initial, fresh.conversation = fixture.project, fixture.initial, fixture.conversation
            fixture = fresh
            if deleted:
                with pytest.raises(BackgroundFailure, match="PROJECT_DELETED"):
                    fixture.coordinator.recover(fixture.project)
            else:
                fixture.coordinator.recover(fixture.project)
            result = "recovered"
        elif deleted:
            with pytest.raises(BackgroundFailure, match="PROJECT_DELETED"):
                fixture.publish(job, proposal)
            result = "rejected"
        else:
            assert fixture.publish(job, proposal).receipt.durable
            committed = True; result = "saved"
        if deleted:
            with fixture.jobs.guard(fixture.project, deleted=True) as directory:
                assert fixture.jobs._read(fixture.project, directory).tombstoned
        else:
            assert len(fixture.current().mutation_replay) == int(committed)
        log.append(dict(action=action, project="A", job="one", result=result, deleted=int(deleted), commits=int(committed)))
    background_evidence(dict(id="NB03:delete-order:" + "-".join(order), seed=0, capacity=1, transitions=3,
        actions=sorted({row["action"] for row in log if row["result"] != "rejected"}), orders=[], log=log, scope="production_integration"))


@pytest.mark.parametrize("order", [("save", "crash", "duplicate"), ("save", "duplicate", "crash"), ("crash", "save", "duplicate")],
    ids=lambda order: "-".join(order))
def test_save_crash_duplicate_schedules_keep_one_commit_and_exact_recovery(tmp_path, order, background_evidence):
    fixture = WriterFixture(tmp_path)
    current = fixture.publication.current()
    change = mutation(current, [put(current, "quote", text="Input across a receipt cut")], "one-stable-input")
    change.capture.session_id = fixture.proof.session_id
    request = WriterMutationV1(**fixture.flush_request(1, [{"cursor": 1, "mutation": change}]).model_dump(by_alias=True), mutation=change)
    saved, log = False, []
    for action in order:
        if action == "crash":
            fresh = fixture.publication.fresh(); fresh.jobs.clock = fixture.wall; fresh.coordinator.authority.clock = fixture.elapsed
            writers = WriterSessions(fresh.coordinator); fresh.coordinator.recover(fresh.project); writers.recover_all()
            fixture.publication, fixture.writers = fresh, writers
            cursor = fresh.jobs.load(fixture.project).writer.acknowledged_cursor
            resumed = fixture.resumed(canonical_revision=fresh.current().project_revision, canonical_sha256=digest_bytes(fresh.current()), action_cursor=cursor)
            fixture.proof = fixture.proof.model_copy(update={"incarnation": resumed.writer.incarnation})
            request = request.model_copy(update={"proof": fixture.proof}, deep=True)
            result = "recovered"
        elif action == "save":
            reached = []
            def fail(name, _project):
                if name == "before_receipt_stored":
                    reached.append(name); raise OSError("Synthetic saved receipt cut")
            fixture.publication.coordinator.observer = fail
            with pytest.raises(BackgroundFailure, match="OUTCOME_UNKNOWN"):
                fixture.writers.save(fixture.project, request)
            assert reached == ["before_receipt_stored"]
            fixture.publication.coordinator.observer = lambda _name, _project: None
            saved, result = True, "unknown_receipt"
        else:
            try:
                view = fixture.writers.save(fixture.project, request)
                result = "exact_replay"
            except BackgroundFailure as error:
                assert error.code == "OUTCOME_UNKNOWN"
                assert len(fixture.publication.current().mutation_replay) == 1
                fixture.publication.coordinator.recover(fixture.project)
                view = fixture.writers.save(fixture.project, request)
                result = "exact_replay_after_recovery"
            assert view.replayed and view.canonical_ready
        actual = fixture.publication.current()
        assert len(actual.mutation_replay) == int(saved)
        if saved: assert block(actual, "quote").content[0].text == "Input across a receipt cut"
        log.append(dict(action=action, project="A", job="one", result=result, commits=int(saved)))
    assert fixture.writers.save(fixture.project, request).replayed
    background_evidence(dict(id="NB03:save-order:" + "-".join(order), seed=0, capacity=1, transitions=3,
        actions=sorted({row["action"] for row in log}), orders=[], log=log, scope="production_integration"))
