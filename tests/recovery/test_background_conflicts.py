"""Positive serial orders, complete reads and monotonic conflict histories."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading

import pytest

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.models.agent import AgentQuery
from packages.resume_core.models.contracts import Source
from packages.resume_core.models.rich_document import NarrativeCitation
from packages.resume_core.models.rich_workspace import RichRenderSnapshot
from packages.resume_core.rich_mutations import RichMutationFailure
from packages.resume_core.rules import RulesStore
from tests.recovery.test_background_inverse import block, mutation, put
from tests.support.background_publication import PublicationFixture


def record(workspace, identifier):
    return next(value for value in workspace.project.facts.records if value.id == identifier)


def record_step(workspace, identifier):
    value = record(workspace, identifier).model_copy(deep=True)
    value.user_corrected = not value.user_corrected
    return {"kind": "put_record", "beforeRevision": value.revision, "record": value}


def apply(fixture, steps, key):
    return fixture.coordinator.manual(fixture.project, mutation(fixture.current(), steps, key),
        originals=fixture.originals, artifacts=fixture.artifact_bytes, images=fixture.images)[0]


def add_source(fixture):
    raw = b"Synthetic source evidence"
    fixture.originals[(fixture.project, "source-one")] = raw
    source = Source(id="source-one", revision=1, originalName="synthetic.txt", mimeType="text/plain",
        byteSha256=hashlib.sha256(raw).hexdigest(), byteRef="sources/source-one.original", parser="text",
        parserVersion="1", units=[{"id": "unit-one", "revision": 1, "order": 0, "text": raw.decode(),
            "location": {"kind": "pasted", "index": 0, "row": None, "column": None}, "disposition": "unresolved",
            "representedFactIds": []}], overlays=[], warnings=[])
    fixture.snapshot(lambda value: value.project.sources.append(source), "source-seed")


@pytest.mark.parametrize("variant", [f"NB-P01:v{index:02d}" for index in range(1, 7)])
def test_positive_disjoint_writes_and_actual_broad_reads(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    queries, steps = None, None
    if variant == "NB-P01:v03":
        queries = [AgentQuery(kind="facts", ids=["candidate-1"])]
        steps = [record_step(fixture.current(), "candidate-1")]
    elif variant == "NB-P01:v05":
        queries = [AgentQuery(kind="document", ids=["narrative", "quote"])]
    job, proposal, _batch = fixture.accepted(queries=queries, steps=steps)
    if variant in {"NB-P01:v01", "NB-P01:v05"}:
        fixture.edit("quote", "Independent block")
    elif variant == "NB-P01:v02":
        value = put(fixture.current(), "narrative", text=block(fixture.current(), "narrative").content[0].text)
        value["block"].content[1].content[0].text = "Different range in the same block"
        apply(fixture, [value], "other-range")
    elif variant == "NB-P01:v03":
        apply(fixture, [record_step(fixture.current(), "language-1")], "unrelated-fact")
    elif variant == "NB-P01:v04":
        fixture.snapshot(lambda value: setattr(value, "title", "Independent title"), "title")
    else:
        raw = b"Synthetic cached artifact"
        fixture.artifact_bytes[(fixture.project, "render-one")] = raw
        def render(value):
            value.project.renders.append(RichRenderSnapshot(id="render-one", documentRevision=value.document_revision,
                factsRevision=value.project.facts.revision, templateSha256="a" * 64, rendererVersion="synthetic",
                rendererSha256="b" * 64, docxSha256=hashlib.sha256(raw).hexdigest(), docxSize=len(raw),
                docxPath="renders/render-one.docx"))
        fixture.snapshot(render, "render-cache")
    manual = fixture.current()
    result = fixture.publish(job, proposal)
    assert result.publication == ("needs_review" if variant in {"NB-P01:v02", "NB-P01:v05"} else "saved")
    current = fixture.current()
    if variant in {"NB-P01:v01", "NB-P01:v05"}:
        assert block(current, "quote").content == block(manual, "quote").content
    elif variant == "NB-P01:v03":
        assert record(current, "language-1") == record(manual, "language-1")
    elif variant == "NB-P01:v04":
        assert current.title == "Independent title"
    elif variant == "NB-P01:v06":
        assert current.project.renders == manual.project.renders


@pytest.mark.parametrize("variant", [f"NB-P02:v{index:02d}" for index in range(1, 4)])
def test_cross_read_write_skew_has_a_valid_serial_winner(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    shared = variant == "NB-P02:v03"
    first = fixture.accepted("a", queries=[AgentQuery(kind="document", ids=["code" if shared else "quote"])])
    second = fixture.accepted("b", queries=[AgentQuery(kind="document", ids=["code" if shared else "narrative"])],
        steps=[put(fixture.current(), "quote", text="Second writer")])
    order = [second, first] if variant == "NB-P02:v02" else [first, second]
    results = [fixture.publish(job, proposal) for job, proposal, _batch in order]
    assert [result.publication for result in results] == (["saved", "saved"] if shared else ["saved", "needs_review"])
    assert len(fixture.current().mutation_replay) == (2 if shared else 1)


@pytest.mark.parametrize("variant", [f"NB-P03:v{index:02d}" for index in range(1, 10)])
def test_every_observed_dependency_can_make_a_proposal_stale(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    queries = [AgentQuery(kind="document", ids=["narrative"])]
    if variant == "NB-P03:v01":
        fixture.snapshot(lambda value: block(value, "narrative").provenance.append(
            NarrativeCitation(kind="citation", id="citation", recordId="job-1", fieldKeys=["role"], evidence=[])), "link")
    elif variant == "NB-P03:v03":
        add_source(fixture)
        queries.append(AgentQuery(kind="source"))
    elif variant == "NB-P03:v06":
        queries.append(AgentQuery(kind="find", text="ABSENT_TOKEN"))
    elif variant == "NB-P03:v07":
        queries.append(AgentQuery(kind="document", ids=["quote"]))
    elif variant in {"NB-P03:v08", "NB-P03:v09"}:
        queries.append(AgentQuery(kind="context"))
    job, proposal, batch = fixture.accepted(queries=queries)
    if variant == "NB-P03:v01":
        apply(fixture, [record_step(fixture.current(), "job-1")], "linked-fact")
    elif variant == "NB-P03:v02":
        value = put(fixture.current(), "narrative")
        value["block"].provenance.append(NarrativeCitation(kind="citation", id="citation", recordId="job-1", fieldKeys=["role"], evidence=[]))
        apply(fixture, [value], "provenance")
    elif variant == "NB-P03:v03":
        fixture.snapshot(lambda value: setattr(value.project.sources[0].units[0], "text", "Changed source"), "source-change")
    elif variant == "NB-P03:v04":
        value = put(fixture.current(), "narrative")
        from packages.resume_core.models.rich_document import FactFieldSpan, InlineStyles
        value["block"].content.append(FactFieldSpan(type="fact_field", bindingId="binding", recordId="job-1",
            fieldKey="role", text="Engineer", styles=InlineStyles(), syncedFactRevision=1))
        apply(fixture, [value], "binding-change")
    elif variant == "NB-P03:v05":
        apply(fixture, [{"kind": "move_block", "blockId": "narrative", "parentId": "header", "afterId": None,
            "beforeRevision": block(fixture.current(), "narrative").revision}], "parent-change")
    elif variant in {"NB-P03:v06", "NB-P03:v07"}:
        fixture.edit("quote", "ABSENT_TOKEN" if variant == "NB-P03:v06" else "Omitted old read")
        assert not batch.read_snapshot_ids
    elif variant == "NB-P03:v08":
        fixture.snapshot(lambda value: setattr(value, "rules_used", RulesStore(tmp_path).load()), "rules")
    else:
        apply(fixture, [{"kind": "move_block", "blockId": "quote", "parentId": "job-section", "afterId": None,
            "beforeRevision": block(fixture.current(), "quote").revision}], "order")
    before = fixture.current()
    assert fixture.publish(job, proposal).publication == "needs_review"
    assert fixture.current() == before
    assert fixture.artifacts.payload_for(fixture.project, proposal.payload)


@pytest.mark.parametrize("variant", [f"NB-P04:v{index:02d}" for index in range(1, 5)])
def test_entity_aba_and_tombstones_cannot_revalidate_an_old_capture(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    before = fixture.current()
    is_fact = variant in {"NB-P04:v02", "NB-P04:v03"}
    queries = [AgentQuery(kind="facts", ids=["language-1"])] if is_fact else None
    job, proposal, _batch = fixture.accepted(queries=queries)
    if variant == "NB-P04:v01":
        fixture.edit("narrative", "Intervening text")
    elif variant == "NB-P04:v02":
        apply(fixture, [record_step(fixture.current(), "language-1")], "fact-change")
    elif variant == "NB-P04:v03":
        apply(fixture, [{"kind": "remove_record", "recordId": "language-1", "beforeRevision": 1}], "fact-delete")
    else:
        apply(fixture, [{"kind": "remove_block", "blockId": "narrative", "beforeRevision": 1}], "block-delete")
    def restore(value):
        if is_fact:
            value.project.facts.records = [item for item in value.project.facts.records if item.id != "language-1"]
            value.project.facts.records.append(record(before, "language-1").model_copy(deep=True))
            value.project.facts.tombstones = [item for item in value.project.facts.tombstones if item.record_id != "language-1"]
        else:
            from packages.resume_core.rich_mutations import locate
            found = locate(value.project.document, "narrative")
            if found:
                found[0].pop(found[1])
            block(value, "job-section").children.insert(0, block(before, "narrative").model_copy(deep=True))
    fixture.snapshot(restore, "restore")
    assert fixture.publish(job, proposal).publication == "needs_review"
    state = fixture.jobs.load(fixture.project)
    assert all(next(value for value in state.generations if value.key == old.key).generation >= old.generation
        for old in proposal.guards.reads)


@pytest.mark.parametrize("variant", [f"NB-P05:v{index:02d}" for index in range(1, 7)])
def test_structural_and_collection_history_keeps_each_member_change(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    queries = [AgentQuery(kind="context")] if variant == "NB-P05:v01" else [AgentQuery(kind="facts")]
    if variant in {"NB-P05:v03", "NB-P05:v04"}:
        if variant == "NB-P05:v04":
            fixture.edit("quote", "QUERY_TOKEN", "query-seed")
        queries = [AgentQuery(kind="find", text="QUERY_TOKEN")]
    if variant == "NB-P05:v02":
        def add_job(value):
            copy = record(value, "job-1").model_copy(deep=True)
            copy.id, copy.periods[0].id = "job-2", "period-2"
            value.project.facts.records.append(copy)
        fixture.snapshot(add_job, "timeline-seed")
    elif variant in {"NB-P05:v05", "NB-P05:v06"}:
        def high_revision(value):
            record(value, "language-1").revision = 900
            value.project.facts.revision = 900
        fixture.snapshot(high_revision, "high-member")
    initial = fixture.current()
    job, proposal, _batch = fixture.accepted(queries=queries)
    if variant == "NB-P05:v01":
        apply(fixture, [{"kind": "move_block", "blockId": "quote", "parentId": "header", "afterId": None,
            "beforeRevision": block(initial, "quote").revision}], "move")
        fixture.snapshot(lambda value: setattr(value.project, "document", initial.project.document.model_copy(deep=True)), "undo-move")
    elif variant == "NB-P05:v02":
        fixture.snapshot(lambda value: value.project.facts.records.reverse(), "reorder")
        fixture.snapshot(lambda value: setattr(value.project.facts, "records", initial.project.facts.records), "restore-order")
    elif variant in {"NB-P05:v03", "NB-P05:v04"}:
        fixture.edit("quote", "QUERY_TOKEN" if variant == "NB-P05:v03" else "Left membership", "query-change")
        fixture.snapshot(lambda value: setattr(block(value, "quote"), "content", block(initial, "quote").content), "query-restore")
    elif variant == "NB-P05:v05":
        apply(fixture, [record_step(fixture.current(), "candidate-1")], "low-member-change")
        assert record(fixture.current(), "language-1").revision == 900
    else:
        apply(fixture, [{"kind": "remove_record", "recordId": "language-1", "beforeRevision": 900}], "delete-max")
    assert fixture.publish(job, proposal).publication == "needs_review"


@pytest.mark.parametrize("variant", ["NB-P06:v01", "NB-P06:v02"])
def test_capture_and_writer_orders_are_coherent(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    if variant == "NB-P06:v01":
        fixture.edit("narrative", "Before capture", "before")
    job, proposal, _batch = fixture.accepted()
    if variant == "NB-P06:v02":
        fixture.edit("narrative", "After capture", "after")
    result = fixture.publish(job, proposal)
    assert result.publication == ("saved" if variant == "NB-P06:v01" else "needs_review")


@pytest.mark.parametrize("variant", [f"NB-P07:v{index:02d}" for index in range(1, 5)])
def test_invalid_whole_batches_never_publish_a_valid_prefix(tmp_path, variant):
    def expand(value):
        block(value, "quote").content[0].text = "Undeclared derived write"
    fixture = PublicationFixture(tmp_path, validate=expand if variant == "NB-P07:v02" else None)
    steps = [put(fixture.current(), "narrative")]
    if variant == "NB-P07:v01":
        steps.append({"kind": "remove_block", "blockId": "missing-final", "beforeRevision": 1})
    elif variant == "NB-P07:v03":
        steps[0]["block"].provenance.append(NarrativeCitation(kind="citation", id="invalid", recordId="missing-record",
            fieldKeys=["role"], evidence=[]))
    elif variant == "NB-P07:v04":
        steps[0]["keepChildren"], steps[0]["afterId"] = False, "missing-anchor"
    job, proposal, _batch = fixture.accepted(steps=steps)
    before = fixture.current()
    with pytest.raises((AgentFailure, BackgroundFailure, RichMutationFailure)):
        fixture.publish(job, proposal)
    assert fixture.current() == before
    assert not fixture.jobs.load(fixture.project).intents
    assert fixture.jobs.read(fixture.project, job.id).publication == "waiting_for_sync"


@pytest.mark.parametrize("variant", [f"NB-P09:v{index:02d}" for index in range(1, 5)])
def test_exact_commit_identity_survives_concurrent_delivery_and_restart(tmp_path, variant):
    fixture = PublicationFixture(tmp_path)
    job, proposal, _batch = fixture.accepted()
    if variant == "NB-P09:v01":
        peer = fixture.fresh()
        barrier = threading.Barrier(2, timeout=10)
        def publish(owner):
            barrier.wait()
            return owner.publish(job, proposal)
        with ThreadPoolExecutor(2) as pool:
            one, two = list(pool.map(publish, [fixture, peer]))
    else:
        one = fixture.publish(job, proposal)
        if variant == "NB-P09:v03":
            fixture.edit("quote", "New independent revision")
        if variant == "NB-P09:v04":
            with pytest.raises(BackgroundFailure, match="JOB_IDEMPOTENCY_CONFLICT"):
                fixture.coordinator.publish(fixture.project, job.id, "b" * 64)
        two = fixture.fresh().publish(job, proposal)
    assert one.receipt == two.receipt and one.receipt.durable
    assert len(fixture.current().mutation_replay) == (2 if variant == "NB-P09:v03" else 1)
