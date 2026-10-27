"""Regression cases for the supplied October 19 review candidates."""

import asyncio
from pathlib import Path
import sys
from copy import deepcopy
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import httpx
import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.models.importing import ImportFact
from packages.resume_core.models.rich_facts import TextField, TechnologyRecord
from packages.resume_core.gui_drafting import DraftField, validate_draft
from packages.resume_core.extraction import parser
from packages.resume_core.extraction.docx_structure import ParagraphStyles
from packages.resume_core.extraction_outcome import has_dated_employment, extraction_report
from packages.resume_core.rendering.layout import _append_with_budget
from packages.resume_core.rich_project_store import RichProjectStore
from tests.extract.test_parser import rebuild
from tests.recovery.draft_fixtures import RULES, draft_request, draft_reply
from tests.recovery.generation_fixtures import render_workspace
from tests.recovery.test_gui_mutations import edit, restore
from tests.recovery.test_rich_persistence import without_sources


@pytest.mark.parametrize("status,value,pending,revision", [
    ("conflict", None, None, 1), ("pending", None, "2 years", 1),
    ("known", "2 years", None, 1), ("unresolved", None, None, 2),
])
def test_experience_nondefault_state_survives_json(status, value, pending, revision):
    field = TextField(value=value, rawText="", status=status, revision=revision, pendingRawText=pending)
    record = TechnologyRecord(id="technology", kind="technology", revision=revision, origin="source", evidence=[],
        jobId=None, subprojectId=None, display=field.model_copy(update={"value": "Python", "status": "known", "pending_raw_text": None}),
        canonicalId=field.model_copy(update={"value": "python", "status": "known", "pending_raw_text": None}), experience=field)
    assert TechnologyRecord.model_validate_json(record.model_dump_json(by_alias=True)).experience == field


@pytest.mark.parametrize("value", ["", " \n\t"])
def test_known_text_must_be_nonblank(value):
    with pytest.raises(ValidationError):
        TextField(value=value, rawText=value, status="known", revision=1, pendingRawText=None)


@pytest.mark.parametrize("record", [None, {"kind": "employment"}, {"kind": "education"}, {"kind": "language", "language": "  "}])
def test_import_fact_needs_meaningful_content(record):
    with pytest.raises(ValidationError):
        ImportFact(id="fact", text=" \n", record=record)
    assert ImportFact(id="fact", text="Retained note", record=record).text == "Retained note"


@pytest.mark.parametrize("target,kind", [("tel:+1234567", "hyperlink"), ("file:///local/image.png", "image"),
                                         ("https://example.invalid/template", "attachedTemplate")])
def test_inert_external_relationship_does_not_reject_visible_docx(target, kind):
    rels = (f'<Relationships xmlns="{parser.R[1:-1]}"><Relationship Id="extra" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{kind}" '
        f'Target="{target}" TargetMode="External"/></Relationships>').encode()
    result = parser.extract(rebuild(extra=("word/_rels/extra.xml.rels", rels)), "source.docx")
    assert any(unit.text == "Привет résumé" for unit in result.units)
    assert all(link.relationship_id != "extra" for link in result.links)


def test_hidden_runs_inherited_styles_and_explicit_visibility():
    styles = ParagraphStyles(ET.fromstring(f'<w:styles xmlns:w="{parser.W[1:-1]}">'
        '<w:style w:styleId="Hidden"><w:rPr><w:vanish/></w:rPr></w:style></w:styles>'))
    paragraph = ET.fromstring(f'<w:p xmlns:w="{parser.W[1:-1]}"><w:pPr><w:pStyle w:val="Hidden"/></w:pPr>'
        '<w:r><w:t>Inherited secret</w:t></w:r>'
        '<w:r><w:rPr><w:vanish w:val="0"/></w:rPr><w:t>Visible</w:t></w:r></w:p>')
    assert parser._paragraph_text(paragraph, styles) == "Visible"
    xml = (f'<w:document xmlns:w="{parser.W[1:-1]}"><w:body><w:p>'
        '<w:r><w:t>Visible</w:t></w:r><w:r><w:rPr><w:vanish/></w:rPr><w:t>Secret</w:t></w:r>'
        '</w:p></w:body></w:document>').encode()
    result = parser.extract(rebuild({"word/document.xml": xml}), "source.docx")
    assert result.units[0].text == "Visible"


def test_unsupported_wrapped_table_row_keeps_later_row_location():
    xml = (f'<w:document xmlns:w="{parser.W[1:-1]}"><w:body><w:tbl><w:tblPr/>'
        '<w:sdt><w:sdtContent><w:tr><w:tc><w:p><w:r><w:t>Skipped</w:t></w:r></w:p></w:tc></w:tr></w:sdtContent></w:sdt>'
        '<w:tr><w:tc><w:p><w:r><w:t>Second row</w:t></w:r></w:p></w:tc></w:tr>'
        '</w:tbl></w:body></w:document>').encode()
    result = parser.extract(rebuild({"word/document.xml": xml}), "source.docx")
    row = next(unit for unit in result.units if unit.text == "Second row")
    assert row.location.row == 1


def test_recovery_count_alone_does_not_copy_source_into_profile():
    request = draft_request()
    request.normalized._native_recovery_count = 1
    request.normalized.facts = [fact for fact in request.normalized.facts if fact.kind not in {"text", "technology", "metric", "leadership"}]
    reply = draft_reply(request, detailed_old=True)
    reply.editorial_plan.focus = []
    for field in reply.fields:
        field.text, field.fact_ids = "", []
    result = validate_draft(request, reply, RULES)
    assert result.document.profile.text.text == ""


def test_unknown_draft_field_is_not_published_as_profile():
    request = draft_request()
    reply = draft_reply(request)
    reply.fields.append(DraftField(fieldId="unknown", text="Unplaced unsupported content", factIds=[]))
    result = validate_draft(request, reply, RULES)
    assert "Unplaced unsupported content" not in result.document.profile.text.text
    assert any(mark.code == "INVALID_DRAFT_FIELD_REFERENCE" for mark in result.annotations)


def test_literal_draft_recovery_excludes_conflicting_facts():
    request = draft_request("E2")
    blocked = {id for conflict in request.normalized.conflicts for id in conflict.fact_ids}
    assert blocked
    for fact in request.normalized.facts:
        if fact.id in blocked and fact.kind == "text":
            fact.value.text = "Conflicting sentinel"
    reply = draft_reply(request, example="E2")
    for field in reply.fields:
        field.text, field.fact_ids = "", []
    result = validate_draft(request, reply, RULES)
    assert "Conflicting sentinel" not in result.document.profile.text.text
    assert not set(result.document.profile.text.fact_ids) & blocked


def test_all_blocked_facts_do_not_trigger_full_source_profile_recovery():
    request = draft_request("E2")
    blocked = {id for conflict in request.normalized.conflicts for id in conflict.fact_ids}
    request.normalized.facts = [fact for fact in request.normalized.facts if fact.id in blocked]
    request.normalized.employment = []
    request.normalized.job_periods = {}
    request.normalized.field_fact_ids = {}
    request.normalized.private_details = []
    for field in (request.normalized.candidate.name, request.normalized.candidate.title, request.normalized.candidate.location):
        field.text = ""
    reply = draft_reply(request, example="E2")
    reply.editorial_plan.focus = []
    for field in reply.fields:
        field.text, field.fact_ids = "", []
    assert validate_draft(request, reply, RULES).document.profile.text.text == ""


def test_focus_label_uses_its_supporting_fact():
    request = draft_request()
    reply = draft_reply(request)
    reply.editorial_plan.focus[0].display = "Invented qualification"
    result = validate_draft(request, reply, RULES, {"python"})
    assert result.document.skills_focus.focus[0].display.text == "Python"


def test_returned_session_text_restores_bindings_without_consuming_older_undo():
    workspace = render_workspace()
    original = workspace.project.document.profile.text.model_copy(deep=True)
    edit(workspace, "profile/text", "First saved edit", completion="slot")
    edit(workspace, "profile/text", "Temporary edit", session="second")
    edit(workspace, "profile/text", "First saved edit", session="second")
    restore(workspace, "profile", "second")
    assert workspace.project.document.profile.text.text == "First saved edit"
    assert workspace.undo_slots["profile"].record.text == original
    restore(workspace, "profile", "second")
    assert workspace.project.document.profile.text == original


def test_return_to_source_spelling_restores_date_parse_and_evidence():
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    field = job.periods[0].start_text
    original = field.model_copy(deep=True)
    header = next(fact for fact in workspace.project.facts if fact.id in field.fact_ids and fact.kind == "employment")
    field.text = header.value.periods[0].start_text = "January 2021"
    original.text = field.text
    edit(workspace, field.field_id, "2022", session="date")
    edit(workspace, field.field_id, original.text, session="date", completion="slot")
    current = workspace.project.document.jobs[0].periods[0].start_text
    assert current == original
    parsed = next(item for item in workspace.derived_state.values if item.field_id == current.field_id)
    assert parsed.valid and parsed.parsed_date.year == 2021


def test_editing_one_field_preserves_other_reconciled_bindings():
    workspace = render_workspace()
    job = workspace.project.document.jobs[0]
    edit(workspace, job.context.field_id, "First edit", completion="slot")
    current = workspace.project.document.jobs[0]
    current.employer.fact_ids, current.employer.evidence, current.employer.origin = [], [], "user"
    employer = current.employer.model_copy(deep=True)
    edit(workspace, current.tasks.field_id, "New tasks", session="second")
    assert workspace.project.document.jobs[0].employer == employer


@pytest.mark.parametrize("height", [616, 660, 705])
def test_first_block_can_use_continuation_page_budget(height):
    pages = [[]]
    _append_with_budget(pages, "large block", height)
    assert pages == [[], [("large block", height)]]


def test_large_first_summary_creates_docx_with_every_source_line(tmp_path):
    from zipfile import ZipFile
    from packages.resume_core.rendering.layout import render_docx
    lines = [f"Retained summary line {number}" for number in range(53)]
    target = tmp_path / "resume.docx"
    render_docx({"source_language": "en", "candidate": {"name": "Candidate", "title": "Engineer",
        "summary": "\n".join(lines)}}, target)
    with ZipFile(target) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    text = "\n".join(node.text or "" for node in document.iter(parser.W + "t"))
    assert all(line in text for line in lines)
    assert any(node.get(parser.W + "type") == "page" for node in document.iter(parser.W + "br"))


def test_ordinary_section_words_do_not_stop_employment_dates():
    source = SimpleNamespace(units=[SimpleNamespace(text="Work experience\nEducation services platform\n2020–2022")])
    assert has_dated_employment([source])
    result = draft_request("E2").normalized
    for source in result.sources:
        for unit in source.units:
            unit.text = "Education services platform"
    report = extraction_report(result, request_bytes=0, recovered_rows=0)
    assert not any(issue.code == "FACT_SECTION_OMITTED" for issue in report.unresolved)


def test_missing_draft_language_follows_english_source():
    from resume_api.gui_draft_input import DraftInput
    request = draft_request()
    for source in request.normalized.sources:
        for unit in source.units:
            unit.text = "Work experience: Software engineer. Built services."
    reply = draft_reply(request).model_dump(by_alias=True)
    del reply["editorialPlan"]["sourceLanguage"]
    del reply["editorialPlan"]["profileLanguage"]
    plan = DraftInput(request).parse(reply).editorial_plan
    assert plan.source_language == plan.profile_language == "en"


def test_rich_cleanup_retries_empty_directory_without_marker(tmp_path, monkeypatch):
    workspace = without_sources()
    store = RichProjectStore(tmp_path)
    store.save(workspace, {}, {})
    store.tombstone(workspace.project_id)
    directory = store.projects / workspace.project_id
    original = type(directory).rmdir
    failed = False
    def interrupted(path):
        nonlocal failed
        if path == directory and not failed:
            failed = True
            raise OSError("interrupted removal")
        return original(path)
    monkeypatch.setattr(type(directory), "rmdir", interrupted)
    assert store.cleanup_deleted(workspace.project_id).cleanup_status == "failed"
    assert not (directory / ".project-identity.json").exists()
    assert store.cleanup_deleted(workspace.project_id).cleanup_status == "complete"
    assert store.cleanup_deleted(workspace.project_id).cleanup_status == "complete"


def test_check_resume_reports_invalid_structure_and_links(tmp_path, monkeypatch):
    from tests.recovery.test_agent_tools import tools_setup, paragraph
    from packages.resume_core.models.rich_document import NarrativeCitation
    session, service, workspace, _ = tools_setup(tmp_path)
    try:
        paragraph(workspace).provenance.append(NarrativeCitation(kind="citation", id="bad-link", recordId="missing", fieldKeys=[], evidence=[]))
        assert session.check()["links"] == "invalid"
        workspace.project.document.revision += 1
        monkeypatch.setattr(service.projects, "read", lambda _identifier: workspace)
        assert session.check()["structure"] == "invalid"
    finally:
        asyncio.run(session.close())


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"{", b'{"duplicate":1,"duplicate":2}', b"\xff"])
async def test_private_mcp_bad_json_returns_client_error(tmp_path, body):
    from tests.recovery.test_agent_tools import tools_setup
    session, _, _, _ = tools_setup(tmp_path)
    listener = session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=listener), base_url="http://" + listener.host) as client:
            response = await client.post("/mcp", content=body, headers={"Authorization": "Bearer " + listener.token})
        assert response.status_code == 400
    finally:
        await session.close()


def test_two_independent_contacts_on_one_pdf_row_remain_separate():
    from packages.resume_core.import_cleanup import compact_contacts
    from packages.resume_core.models.contracts import SourceStructure
    from tests.recovery.test_import_content import paragraphs_fixture
    sources, _, _ = paragraphs_fixture(["one@example.test", "+1234567"], pages=[1, 1])
    blocks, metadata = [], {}
    for index, unit in enumerate(sources[0].units):
        unit.structure = SourceStructure(bounds=[10 + index * 100, 20, 90 + index * 100, 30])
        blocks.append({"id": str(index), "type": "paragraph", "content": [{"type": "text", "text": unit.text}],
            "provenance": [{"kind": "source", "evidence": [{"sourceId": sources[0].id, "unitId": unit.id}]}]})
        metadata[str(index)] = SimpleNamespace(category="contacts", id=f"outline_0_p{index}")
    assert compact_contacts(deepcopy(blocks), metadata, sources) == blocks


def test_subproject_exposure_survives_a_date_edit_in_an_ongoing_job():
    from packages.resume_core.dates import partial_date
    from packages.resume_core.models.contracts import Period, Subproject
    from packages.resume_core.gui_derived import initial_derived
    workspace = render_workspace()
    document = workspace.project.document
    job = workspace.project.employment[0]
    technology = next(fact for fact in workspace.project.facts if fact.kind == "technology" and fact.job_id == job.id)
    job.subprojects.append(Subproject(id="sub", name="Dated work", factIds=[technology.id],
        period=Period(start=partial_date("2022-01"), end=partial_date("2022-12"))))
    technology.subproject_id = "sub"
    entry = document.skills_focus.focus[0]
    entry.fact_ids = [technology.id]
    document.jobs[0].periods[0].start_text.text = "2020"
    document.jobs[0].periods[0].start_text.origin = "user"
    derived = initial_derived(document, workspace.project.facts, workspace.project.employment, None, 1, "en")
    exposure = next(item for item in derived.values if item.field_id == entry.display.field_id)
    assert exposure.complete_exposure and exposure.months_min == exposure.months_max == 12


def test_focus_reconciliation_updates_display_and_duration_references_together():
    from packages.resume_core.gui_reconciliation import GuiReconcileProposal, apply_reconciliation, result_dependencies
    from tests.recovery.generation_fixtures import frozen_now
    workspace = render_workspace()
    entry = workspace.project.document.skills_focus.focus[0]
    source = next(fact for fact in workspace.project.facts if fact.kind == "technology" and fact.value.canonical_id == entry.catalog_id)
    another = source.model_copy(update={"id": "another-exposure", "job_id": workspace.project.employment[1].id,
        "origin": "user", "evidence": []}, deep=True)
    workspace.project.facts.append(another)
    ids = [another.id]
    proposal = GuiReconcileProposal(facts=[], fieldFacts=[{"fieldId": entry.display.field_id, "factIds": ids}],
        annotations=[], suggestions=[], editorialPlan=None, recommendations=[])
    assert apply_reconciliation(workspace, [entry.display.field_id], proposal, result_dependencies(workspace, RULES), RULES, frozen_now().isoformat())
    current = workspace.project.document.skills_focus.focus[0]
    assert current.fact_ids == current.display.fact_ids == ids


def test_local_v5_save_enforces_portable_workspace_size(tmp_path, monkeypatch):
    from packages.resume_core import archive_zip
    from packages.resume_core.gui_projects import GuiProjectStore
    from packages.resume_core.project_store import ProjectStoreFailure
    workspace = render_workspace()
    workspace.project.sources = []
    store = GuiProjectStore(tmp_path)
    store.save(workspace, {}, {})
    path = store.projects / workspace.project_id / "workspace.json"
    before = path.read_bytes()
    monkeypatch.setattr(archive_zip, "MAX_JSON", 10)
    with pytest.raises(ProjectStoreFailure, match="PROJECT_TOO_LARGE"):
        store.save(workspace, {}, {})
    assert path.read_bytes() == before


def test_loading_shared_catalog_does_not_delete_a_supported_foreign_version(tmp_path):
    from packages.resume_core.gui_projects import GuiProjectStore
    workspace = without_sources()
    RichProjectStore(tmp_path).save(workspace, {}, {})
    _, errors, registry = GuiProjectStore(tmp_path).load_all()
    assert workspace.project_id in errors
    assert not any(entry.tombstoned for entry in registry.entries)
    loaded, errors, _ = RichProjectStore(tmp_path).load_all()
    assert not errors and loaded[workspace.project_id][0] == workspace


def test_full_block_rewrite_keeps_nested_children_exactly():
    from packages.resume_core.rich_sync import RichRewriteProposal, rewrite_steps
    from packages.resume_core.rich_mutations import apply_rich_mutation
    from tests.recovery.test_rich_synchronization import selection, mutation
    workspace = without_sources()
    parent = next(block for block in workspace.project.document.blocks() if block.id == "bullet")
    selected = selection(workspace, "bullet", end=0).model_copy(update={"kind": "blocks"})
    output = parent.model_copy(deep=True)
    output.content[0].text = "Changed parent"
    output.children = []
    proposal = RichRewriteProposal(replacements=[{"blockId": parent.id, "blocks": [output]}])
    changed, _ = apply_rich_mutation(workspace, mutation(workspace, rewrite_steps(workspace, selected, proposal)))
    current = next(block for block in changed.project.document.blocks() if block.id == parent.id)
    assert current.content[0].text == "Changed parent"
    assert current.children == parent.children


def test_removing_period_retains_other_edits_in_the_same_block():
    from packages.resume_core.models.rich_document import FactFieldSpan, StyledText
    from packages.resume_core.models.rich_mutations import PutBlock
    from packages.resume_core.rich_panel import period_blocks, put_block
    from packages.resume_core.rich_dependencies import placements
    workspace = without_sources()
    project = workspace.project
    record = project.facts.records[1]
    old = record.model_copy(deep=True)
    block = next(block for block in project.document.blocks() if block.id == "narrative")
    block.content = [FactFieldSpan(type="fact_field", bindingId="remove", bindingRootId="root", recordId=record.id,
        fieldKey=f"period:{record.periods[0].id}:start", text="2020", syncedFactRevision=1, styles={}),
        StyledText(type="text", text="Old employer", styles={})]
    staged = block.model_copy(deep=True)
    staged.content[-1].text = "New employer"
    record.periods = []
    positions = placements(project.document)
    steps = period_blocks(project, record, old, [put_block(staged, positions)], positions)
    updated = next(step.block for step in steps if isinstance(step, PutBlock) and step.block.id == block.id)
    assert len(updated.content) == 1 and updated.content[0].text == "New employer"


@pytest.mark.asyncio
async def test_completed_before_deadline_is_valid_when_observed_after_deadline():
    from packages.resume_core.background_clock import ControlledDeadlines
    from packages.resume_core.background_supervisor import JobSupervisor, JobControl, ExecutionOutcome
    supervisor = object.__new__(JobSupervisor)
    supervisor.clock = ControlledDeadlines()
    control = JobControl(supervisor, None, startup_deadline=15, active_deadline=180)
    started, release = asyncio.Event(), asyncio.Event()
    async def run(_control):
        started.set()
        await release.wait()
        return ExecutionOutcome(finished_at=179)
    task = asyncio.create_task(supervisor._wait_run(control, SimpleNamespace(run=run)))
    control.ready.set()
    await started.wait()
    await asyncio.sleep(0)
    supervisor.clock.advance(181)
    release.set()
    result, owned = await task
    assert result.state == "completed" and result.error is None
    await owned
    supervisor.clock.verify()


@pytest.mark.parametrize("name", ["read_public_page", "publish_findings", "project_action", "apply_edit_batch"])
@pytest.mark.asyncio
async def test_malformed_known_tool_arguments_are_not_permission_denials(tmp_path, name):
    from tests.recovery.test_agent_tools import tools_setup
    session, _, _, _ = tools_setup(tmp_path)
    try:
        error = session.preflight({"name": name, "arguments": {"request": {}}})
        assert error == "AGENT_ARGUMENT_INVALID"
        assert session.preflight_failure(error)["argumentIssues"]
    finally:
        await session.close()


def test_failed_run_keeps_its_failure_cause_in_prepared_receipt(tmp_path):
    from tests.support.agent import isolated_project
    from tests.recovery.test_agent_store import submit, prepared, prepare_request
    from packages.resume_core.models.agent import AgentPrepareResult
    from packages.resume_core.agent_store import run_in
    store, _, workspace, conversation = isolated_project(tmp_path)
    run, _ = submit(store, workspace, conversation)
    batch = prepared(run, workspace)
    result = AgentPrepareResult(disposition="prepared", batchId=batch.id, affected=[], preview="Updated")
    store.prepare(workspace.project_id, run.id, prepare_request(), lambda *_: (result, batch))
    store.finish(workspace.project_id, run.id, "failed", error="AGENT_PROTOCOL")
    _, _, journal = run_in(store.load(workspace.project_id), run.id)
    assert journal.batches[0].receipt.error.code == "AGENT_PROTOCOL"


@pytest.mark.asyncio
async def test_saved_commit_replays_after_a_later_save_with_exact_mutation_proof(tmp_path):
    from tests.recovery.test_agent_publication import staged, manual
    from packages.resume_core.models.agent import AgentCommitResult
    session, service, workspace, batch, offer, request = await staged(tmp_path)
    try:
        first = service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        assert (await offer).durable
        service.projects.mutate(workspace.project_id, manual(service.projects.read(workspace.project_id)))
        replay = service.publication.commit(workspace.project_id, session.run.id, batch.id, request)
        assert replay.receipt == first.receipt
        assert replay.project.workspace.project_revision > replay.receipt.project_revision
        invalid = replay.model_dump(by_alias=True)
        invalid["receipt"]["requestSha256"] = "0" * 64
        with pytest.raises(ValidationError):
            AgentCommitResult.model_validate(invalid)
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["records", "updates", "uncertain"])
async def test_model_reconciliation_cannot_overwrite_deterministic_record_edits(tmp_path, monkeypatch, mode):
    from packages.resume_core.models.rich_document import NarrativeCitation
    from packages.resume_core.models.rich_facts import ClaimRecord
    from packages.resume_core.models.rich_mutations import PutRecord
    from packages.resume_core.rich_sync import RichReconcileProposal
    from tests.recovery.test_rich_images_service import service
    from tests.recovery.test_rich_synchronization import completion
    import resume_api.rich_synchronization as synchronization
    instance, identifier = service(tmp_path)
    workspace = instance.workspaces[identifier]
    candidate = workspace.project.facts.records[0]
    claim = ClaimRecord(kind="claim", id="claim", revision=1, origin="source", evidence=[], jobId=None,
        subprojectId=None, value={"value": "Source claim", "rawText": "Source claim", "status": "known", "revision": 1, "pendingRawText": None})
    workspace.project.facts.records.append(claim)
    block = next(block for block in workspace.project.document.blocks() if block.id == "narrative")
    block.provenance = [NarrativeCitation(kind="citation", id=f"cite-{record.id}", recordId=record.id, fieldKeys=[], evidence=[])
        for record in (candidate, claim)]
    deterministic = candidate.model_copy(deep=True)
    deterministic.title.raw_text = deterministic.title.value = "Exact edited title"
    monkeypatch.setattr(synchronization, "exact_completion", lambda *_: ([PutRecord(kind="put_record",
        beforeRevision=candidate.revision, record=deterministic)], []))
    async def interpret(*_args):
        record = candidate.model_copy(deep=True)
        record.title.raw_text = record.title.value = "Unwanted replacement"
        values = {"updates": [], "records": [], "uncertain": []}
        values[mode] = [record] if mode == "records" else [{"recordId": candidate.id, "fieldKey": "title", "text": "Unwanted replacement"}]
        return RichReconcileProposal(**values)
    monkeypatch.setattr(instance, "sync_content", interpret)
    reply = await instance.complete_rich(identifier, completion(blockIds=[block.id], interpret=True))
    sync = reply.workspace.sync_records[-1]
    assert sync.status == "failed"
    exact = next(step.record for step in sync.proposed_steps if isinstance(step, PutRecord))
    assert exact.title.value == "Exact edited title"
