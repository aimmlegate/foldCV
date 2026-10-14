"""Complete controlled drafts apply captured plans, never legacy cutoff logic."""

import copy
import json
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_drafting import DraftField, GuiDraftProposal, drafting_input, validate_draft, replace_focus_warnings, DraftFailure
from packages.resume_core.rules import RulesStore
from packages.resume_core.models.recovery import GuiTechnologyFact
from resume_api.gui_drafting_content import GuiDraftingContentService
from resume_api.lifecycle import OperationFiles
from resume_api.providers.content import ContentResult, ReportedUsage, ContentFailure
from tests.recovery.draft_fixtures import RULES, draft_request, draft_reply


class DraftProvider:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def generate(self, content, _files, _cancel):
        self.calls.append(json.loads(content.text))
        assert content.result_type is GuiDraftProposal and content.policy.allow_repair is False
        return ContentResult(self.reply, ReportedUsage(), "fixture", content.policy.model, 0.1, 1)


@pytest.mark.parametrize("example", ["E1", "E2"])
def test_complete_document_applies_supplied_plan_with_all_jobs_in_prompt(example, tmp_path, monkeypatch):
    from packages.resume_core import dates, drafting, selection
    from packages.resume_core.rendering import preparation

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy editorial helper entered GUI path")

    monkeypatch.setattr(dates, "old_job", forbidden)
    monkeypatch.setattr(drafting, "_recent_jobs", forbidden)
    monkeypatch.setattr(selection, "old_job", forbidden)
    monkeypatch.setattr(preparation, "prepare_document", forbidden)
    request = draft_request(example)
    reply = draft_reply(request, example=example)
    provider = DraftProvider(reply)
    result, usage = GuiDraftingContentService(provider, "fixture").run(request, RULES, OperationFiles(tmp_path), threading.Event())
    assert len(provider.calls) == usage["logicalAttempts"] == 1
    assert len(provider.calls[0]["input"]["activeJobs"]) == (3 if example == "E1" else 2)
    assert result.document.candidate.name.text == ("Ирина Примерова" if example == "E1" else "Алексей")
    assert result.document.profile.text.text.startswith("Разрабатываю")
    represented = {job.id for job in result.document.jobs} | set(result.document.early_career.represented_job_ids)
    assert represented == {job.id for job in request.normalized.employment}
    assert result.editorial_plan.profile_language == "ru"
    assert result.editorial_plan.source_language == ("ru" if example == "E1" else "mixed")
    if example == "E1":
        assert len(result.document.jobs) == 2 and len(result.document.early_career.represented_job_ids) == 1
        assert len(result.document.education) == 1 and len(result.document.languages) == 2
        assert "100 до 70 мс" in result.document.jobs[0].results.text and "30%" in result.document.jobs[0].results.text
        assert result.document.skills_focus.skills_text.text == "Docker"
    else:
        assert result.document.education == result.document.languages == []
        assert result.document.jobs[0].periods == []
        assert "ExampleDB-X" in result.document.jobs[0].stack.text
        assert result.document.skills_focus.skills_text.text == "Rust"
        assert all(not set(field.fact_ids) & {id for conflict in request.normalized.conflicts for id in conflict.fact_ids}
                   for job in result.document.jobs for field in (job.context, job.tasks, job.results))


def test_saved_twenty_year_rules_reach_all_jobs_and_fixed_plan_keeps_old_job_detailed(tmp_path):
    store = RulesStore(tmp_path / "FoldCV")
    initial = store.load()
    changed = store.save(initial.markdown.replace("15 years", "20 years"), initial.revision)
    request = draft_request()
    provider = DraftProvider(draft_reply(request, rules_revision=changed.revision, detailed_old=True))
    result, _usage = GuiDraftingContentService(provider, "fixture").run(request, changed, OperationFiles(tmp_path), threading.Event())
    assert provider.calls[0]["rulesUsed"]["revision"] == changed.revision
    assert "20 years" in provider.calls[0]["rulesUsed"]["markdown"]
    assert [job.employer.text for job in result.document.jobs] == ["Север", "Запад", "Восток"]
    assert result.document.early_career.represented_job_ids == []
    assert len(provider.calls) == 1


def test_focus_removals_are_located_replaceable_warnings_without_extra_calls():
    request = draft_request()
    raw = draft_reply(request).model_dump(by_alias=True)
    python = raw["editorialPlan"]["focus"][0]
    postgres = next(fact for fact in request.normalized.facts if isinstance(fact, GuiTechnologyFact) and fact.value.canonical_id == "postgresql")
    raw["editorialPlan"]["focus"] = [python, copy.deepcopy(python), {"catalogId": "unknown-tool", "display": "Unknown", "factIds": []},
        {"catalogId": "postgresql", "display": "PostgreSQL", "factIds": [postgres.id]}]
    reply = GuiDraftProposal.model_validate(raw)
    result = validate_draft(request, reply, RULES, available_logos={"python"})
    assert [entry.catalog_id for entry in result.document.skills_focus.focus] == ["python"]
    warning = result.annotations[0]
    assert warning.type == "warning" and warning.code == "focus_entry_removed" and warning.anchor.section_id == "skills-focus"
    assert [removed.reason for removed in warning.removed_focus] == ["duplicate", "unknown-ID", "missing-logo"]
    assert replace_focus_warnings(result.annotations, result.annotations) == result.annotations
    clean = validate_draft(request, draft_reply(request), RULES, available_logos={"python"})
    assert replace_focus_warnings(result.annotations, clean.annotations) == []
    assert "PostgreSQL" in result.document.jobs[0].stack.text


@pytest.mark.parametrize("change,code", [
    ("job", "INVALID_EDITORIAL_PLAN_CONTEXT"), ("facts", "INVALID_EDITORIAL_FACT_REFERENCE"),
    ("field", "INVALID_DRAFT_FIELD_REFERENCE"), ("fields", "INCOMPLETE_DRAFT_FIELDS"),
])
def test_broken_plan_or_field_references_fail_without_repair(change, code, tmp_path):
    request = draft_request()
    raw = draft_reply(request).model_dump(by_alias=True)
    if change == "job": raw["editorialPlan"]["jobs"].pop()
    if change == "facts": raw["editorialPlan"]["factIds"].append("foreign fact")
    if change == "field": raw["fields"][0]["fieldId"] = "foreign field"
    if change == "fields": raw["fields"].pop()
    provider = DraftProvider(GuiDraftProposal.model_validate(raw))
    with pytest.raises(ContentFailure) as error:
        GuiDraftingContentService(provider, "fixture").run(request, RULES, OperationFiles(tmp_path), threading.Event())
    assert error.value.code == code and error.value.logical_attempts == 1
    assert len(provider.calls) == 1


def test_focus_capacity_keeps_first_eight_in_supplied_order():
    from packages.resume_core.models.recovery import GuiTechnologyFact
    from packages.resume_core.technologies import BY_ID

    request = draft_request()
    raw = draft_reply(request).model_dump(by_alias=True)
    base = next(fact for fact in request.normalized.facts if isinstance(fact, GuiTechnologyFact))
    order = list(BY_ID)[:9]
    entries = []
    for id in order:
        data = base.model_dump(by_alias=True)
        data.update(id="focus-fact-" + id, jobId=None, subprojectId=None)
        data["value"] = {"canonicalId": id, "display": id, "scope": "global"}
        fact = GuiTechnologyFact.model_validate(data)
        request.normalized.facts.append(fact)
        entries.append({"catalogId": id, "display": id, "factIds": [fact.id]})
    raw["editorialPlan"]["focus"] = entries
    result = validate_draft(request, GuiDraftProposal.model_validate(raw), RULES, available_logos=set(order))
    assert [entry.catalog_id for entry in result.document.skills_focus.focus] == order[:8]
    assert result.annotations[0].removed_focus[0].reason == "capacity"
    assert len(request.normalized.facts) > len(result.document.skills_focus.focus)


def test_draft_payload_and_skeleton_preserve_candidate_details():
    from packages.resume_core.gui_normalization import GuiSemanticProposal, normalize_candidate
    from packages.resume_core.gui_employment import normalize_employment
    from packages.resume_core.gui_drafting import GuiDraftRequest, draft_skeleton
    from tests.recovery.candidate_fixtures import ROOT, request as normalization_request, value
    from tests.recovery.employment_fixtures import employment_proposal

    source = normalization_request((ROOT / "E1.txt").read_text() + "Email: fictional@example.invalid\n")
    raw = employment_proposal(source).model_dump(by_alias=True)
    raw["privateDetails"] = [{"kind": "email", "value": value(source.sources[0], "fictional@example.invalid")}]
    reply = GuiSemanticProposal.model_validate(raw)
    normalized = normalize_employment(source, reply, normalize_candidate(source, reply, RULES))
    request = GuiDraftRequest.model_validate({"projectId": "private-draft", "projectRevision": 1, "documentRevision": 1,
        "normalized": normalized.model_dump(by_alias=True), "formattingAsOf": source.formatting_as_of.model_dump(by_alias=True)})
    assert "fictional@example.invalid" in drafting_input(request, RULES)
    assert draft_skeleton(normalized).candidate.details[0].text == "fictional@example.invalid"
    assert "fictional@example.invalid" in normalized.sources[0].units[-1].text


def test_editorial_context_has_exact_date_bounds_and_age_days_without_invented_components():
    request = draft_request()
    payload = json.loads(drafting_input(request, RULES))["input"]
    old = payload["activeJobs"][2]["periodBounds"][0]
    assert old["startLower"] == [2008, 1, 1] and old["startUpper"] == [2008, 12, 31]
    assert old["endLower"] == [2009, 1, 1] and old["endUpper"] == [2009, 12, 31]
    assert old["daysSinceEndBounds"][0] < old["daysSinceEndBounds"][1]
    present = payload["activeJobs"][0]["periodBounds"][0]
    assert present["endLower"] is None and present["daysSinceEndBounds"] is None
    assert payload["activeJobs"][0]["periods"][0]["start"]["precision"] == "year"


@pytest.mark.parametrize("field_id", ["candidate/name", "candidate/title", "candidate/location"])
def test_drafting_cannot_replace_supported_identity_with_unrelated_facts(field_id):
    request = draft_request()
    reply = draft_reply(request)
    title = next(fact for fact in request.normalized.facts
                 if fact.kind == "candidate_detail" and fact.value.field == "title")
    reply.fields.append(DraftField(fieldId=field_id, text="Invented Unsupported Surname", factIds=[title.id]))
    with pytest.raises(DraftFailure, match="DRAFT_STRUCTURED_FIELD"):
        validate_draft(request, reply, RULES)


@pytest.mark.parametrize("scope", ["all", "profile", "job-prose", "job-stack", "skills"])
def test_present_field_ids_cannot_hide_empty_supported_prose(scope):
    request = draft_request()
    reply = draft_reply(request, detailed_old=True)
    first = request.normalized.employment[0].id
    for field in reply.fields:
        if (scope == "all" or scope == "profile" and field.field_id == "profile/text"
            or scope == "job-prose" and field.field_id in {f"job:{first}/{key}" for key in ("context", "tasks", "results")}
            or scope == "job-stack" and field.field_id == f"job:{first}/stack"
            or scope == "skills" and field.field_id == "skills-focus/skillsText"):
            field.text = " \n "
            field.fact_ids = []
    with pytest.raises(DraftFailure, match="EMPTY_SUPPORTED_DRAFT_PROSE"):
        validate_draft(request, reply, RULES)


def test_empty_prose_is_allowed_when_only_structured_source_facts_exist():
    request = draft_request()
    request.normalized.facts = [fact for fact in request.normalized.facts
                                if fact.kind not in {"text", "technology", "metric", "leadership", "date"}]
    reply = draft_reply(request, detailed_old=True)
    reply.editorial_plan.focus = []
    reply.editorial_plan.technology_groups = []
    for field in reply.fields:
        field.text = ""
        field.fact_ids = []
    result = validate_draft(request, reply, RULES)
    assert result.document.candidate.name.text == "Ирина Примерова"
    assert len(result.document.jobs) == 3
