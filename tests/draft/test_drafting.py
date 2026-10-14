"""Synthetic prose selection and one-call content boundary."""

from __future__ import annotations

import json
from pathlib import Path
import threading
import sys

import pytest

from packages.resume_core.drafting import DraftProposal, DraftRequest, draft_input, draft_selection, validate_draft
from packages.resume_core.normalization import FactSheet
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from resume_api.drafting_content import DraftingContentService
from resume_api.lifecycle import OperationFiles
from resume_api.providers.content import ContentResult, ReportedUsage


ROOT = Path(__file__).resolve().parents[2]


def request_with_jobs() -> DraftRequest:
    sheet = json.loads((ROOT / "contracts/examples/fact_sheet.json").read_text())
    source = sheet["units"][0]["sourceId"]
    unit = sheet["units"][0]["unitId"]
    period = lambda start, end: {"start": {"precision": "year", "year": start, "month": None, "day": None},
                                 "end": {"precision": "year", "year": end, "month": None, "day": None}}
    sheet["employment"] = [
        {"id": "recent", "employer": "Recent Company", "role": "Engineer", "periods": [period(2021, 2025)],
         "sourceId": source, "unitIds": [unit], "subprojects": [], "factIds": ["recent_text", "recent_metric"]},
        {"id": "older", "employer": "Older Company", "role": "Engineer", "periods": [period(2000, 2004)],
         "sourceId": source, "unitIds": [unit], "subprojects": [], "factIds": ["older_text"]},
    ]
    for id_, job, text, importance in [("recent_text", "recent", "Built a service.", "essential"),
                                        ("older_text", "older", "Maintained a system.", "normal"),
                                        ("global_strength", None, "Designed reliable systems.", "essential"),
                                        ("contact", None, "email: private@example.test", "essential")]:
        sheet["facts"].append({"id": id_, "revision": 1, "kind": "text", "value": {"text": text},
                               "evidence": [], "origin": "user", "importance": importance,
                               "jobId": job, "subprojectId": None})
    sheet["facts"].append({"id": "recent_metric", "revision": 1, "kind": "metric",
                           "value": {"number": 20, "upperNumber": None, "comparator": "at_most", "unit": "requests",
                                     "period": "day", "baseline": None, "result": None, "scope": "service",
                                     "attribution": "team", "qualifiers": ["peak"]},
                           "evidence": [], "origin": "user", "importance": "essential",
                           "jobId": "recent", "subprojectId": None})
    return DraftRequest(sheet=FactSheet.model_validate(sheet), sourceFingerprint=sheet["sourceFingerprint"],
                        baseRevision=sheet.get("revision", 1), sourceLanguage="mixed",
                        asOf={"precision": "day", "year": 2026,
                                                                        "month": 10, "day": 11})


def proposal() -> DraftProposal:
    return DraftProposal(blocks=[
        {"blockId": "profile", "text": "Built a service. team peak at most 20 requests per day in the service. Designed reliable systems.",
         "factIds": ["recent_text", "recent_metric", "global_strength"]},
        {"blockId": "prose_recent", "text": "Built a service. team peak at most 20 requests per day in the service.",
         "factIds": ["recent_text", "recent_metric"]},
    ])


def test_selection_bounds_prompt_and_keeps_contacts_without_old_work():
    request = request_with_jobs()
    selection = draft_selection(request)
    assert set(selection) == {"profile", "prose_recent"}
    prompt = draft_input(request)
    assert "global_strength" in prompt and "recent_metric" in prompt
    assert "private@example.test" in prompt
    assert "evidence" not in prompt and "sourceFingerprint" not in prompt
    assert "Maintained a system" not in prompt
    assert '"sourceLanguage":"mixed"' in prompt
    huge = request.model_copy(deep=True)
    huge.sheet.facts[-1].value.qualifiers = ["long" * 20_000]
    with pytest.raises(ValueError, match="INPUT_TOO_LARGE"):
        draft_input(huge)


@pytest.mark.parametrize("origin", ["source", "user"])
def test_cited_text_fact_with_unverified_wording_needs_source_review(origin):
    request = request_with_jobs()
    fact = next(fact for fact in request.sheet.facts if fact.id == "recent_text")
    fact.origin = origin
    draft = proposal()
    draft.blocks[1].text = "Worked on a team. team peak at most 20 requests per day in the service."
    result = validate_draft(request, draft)
    assert any(issue.code == "SOURCE_REVIEW" and issue.block_id == "prose_recent" and
               issue.fact_id == "recent_text" for issue in result.issues)
    assert not any(issue.code == "SOURCE_REVIEW" and issue.block_id == "profile" and
                   issue.fact_id == "recent_text" for issue in result.issues)


def test_all_recent_jobs_and_facts_are_selected_without_silent_truncation():
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    recent = sheet["employment"][0]
    more = {**recent, "id": "another_recent", "factIds": ["another_fact"]}
    sheet["employment"].append(more)
    sheet["facts"].append({"id": "another_fact", "revision": 1, "kind": "text",
                           "value": {"text": "Shipped another service."}, "evidence": [], "origin": "user",
                           "importance": "normal", "jobId": "another_recent", "subprojectId": None})
    selection = draft_selection(request.model_copy(update={"sheet": FactSheet.model_validate(sheet)}))
    assert "prose_another_recent" in selection
    assert "another_fact" in [fact.id for fact in selection["profile"]]
    for index in range(201):
        sheet["facts"].append({"id": f"fact_{index}", "revision": 1, "kind": "text",
                               "value": {"text": f"Fact {index}"}, "evidence": [], "origin": "user",
                               "importance": "normal", "jobId": "recent", "subprojectId": None})
        sheet["employment"][0]["factIds"].append(f"fact_{index}")
    oversized = request.model_copy(update={"sheet": FactSheet.model_validate(sheet)})
    assert len(draft_selection(oversized)["profile"]) > 200
    with pytest.raises(ValueError, match="INPUT_TOO_LARGE"):
        draft_input(oversized)


def test_job_attached_contacts_reach_scoped_provider_payload():
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    sheet["facts"].append({"id": "job_contact", "revision": 1, "kind": "text",
                           "value": {"text": "phone: +12345678901"}, "evidence": [], "origin": "user",
                           "importance": "essential", "jobId": "recent", "subprojectId": None})
    sheet["employment"][0]["factIds"].append("job_contact")
    scoped = request.model_copy(update={"sheet": FactSheet.model_validate(sheet)})
    assert "job_contact" in draft_input(scoped)


@pytest.mark.parametrize("contact", [
    "Call 555-123-4567 for references.",
    "Reach me at (555) 123 4567.",
    "Reach me at 555.123.4567.",
    "Reach me at +44 20 7123 4567.",
    "Reach me at +7 (999) 123-45-67.",
    "Local line 123-4567.",
    "Portfolio: https://example.invalid/contact",
    "Profile at linkedin.com/in/example",
    "phone: 5551234567",
])
def test_unlabeled_and_marked_contacts_remain_in_selected_draft_blocks(contact):
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    sheet["facts"].append({"id": "job_contact", "revision": 1, "kind": "text",
                           "value": {"text": contact}, "evidence": [], "origin": "user",
                           "importance": "essential", "jobId": "recent", "subprojectId": None})
    sheet["employment"][0]["factIds"].append("job_contact")
    scoped = request.model_copy(update={"sheet": FactSheet.model_validate(sheet)})
    payload = draft_input(scoped)
    assert "job_contact" in payload
    assert contact in payload


def test_numeric_work_and_date_context_remain_selectable():
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    next(fact for fact in sheet["facts"] if fact["id"] == "recent_metric")["value"]["number"] = 5551234567
    sheet["facts"].append({"id": "job_numbers", "revision": 1, "kind": "text",
                           "value": {"text": "From 2021-2025, processed +20 000 records per day."},
                           "evidence": [], "origin": "user", "importance": "essential",
                           "jobId": "recent", "subprojectId": None})
    sheet["employment"][0]["factIds"].append("job_numbers")
    payload = draft_input(request.model_copy(update={"sheet": FactSheet.model_validate(sheet)}))
    assert "job_numbers" in payload
    assert "+20 000 records per day" in payload
    assert '"number":5551234567' in payload


@pytest.mark.parametrize("private", ["Age: 29", "Дата рождения: 1997", "Resume ID: 12345", "Job board: hh.ru"])
def test_labeled_age_and_job_board_metadata_remain_selected(private):
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    sheet["facts"].append({"id": "private_metadata", "revision": 1, "kind": "text",
                           "value": {"text": private}, "evidence": [], "origin": "user",
                           "importance": "essential", "jobId": "recent", "subprojectId": None})
    sheet["employment"][0]["factIds"].append("private_metadata")
    payload = draft_input(request.model_copy(update={"sheet": FactSheet.model_validate(sheet)}))
    assert "private_metadata" in payload
    assert private in payload


@pytest.mark.parametrize("site", ["Portfolio: alice.dev", "Website: alice.com", "LinkedIn: linkedin.com"])
def test_labeled_personal_site_and_other_facts_remain_selected(site):
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    sheet["facts"].append({"id": "personal_site", "revision": 1, "kind": "text",
                           "value": {"text": site}, "evidence": [], "origin": "user",
                           "importance": "essential", "jobId": "recent", "subprojectId": None})
    sheet["employment"][0]["factIds"].append("personal_site")
    original = json.loads(json.dumps(sheet))
    payload = draft_input(request.model_copy(update={"sheet": FactSheet.model_validate(sheet)}))
    assert "personal_site" in payload and site in payload
    assert "recent_text" in payload and "recent_metric" in payload
    assert sheet == original


def test_experience_and_technical_job_board_mentions_remain_selectable():
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    sheet["facts"].append({"id": "work_context", "revision": 1, "kind": "text",
                           "value": {"text": "12 years of experience building hh.ru integrations in 2022-2025."},
                           "evidence": [], "origin": "user", "importance": "essential",
                           "jobId": "recent", "subprojectId": None})
    sheet["employment"][0]["factIds"].append("work_context")
    assert "work_context" in draft_input(request.model_copy(update={"sheet": FactSheet.model_validate(sheet)}))


@pytest.mark.parametrize("contact", ["Call 5551234567 for references.", "5551234567"])
def test_bare_domestic_phone_forms_remain_selected(contact):
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    sheet["facts"].append({"id": "bare_contact", "revision": 1, "kind": "text",
                           "value": {"text": contact}, "evidence": [], "origin": "user",
                           "importance": "essential", "jobId": "recent", "subprojectId": None})
    sheet["employment"][0]["factIds"].append("bare_contact")
    scoped = request.model_copy(update={"sheet": FactSheet.model_validate(sheet)})
    assert "bare_contact" in draft_input(scoped)
    assert contact in draft_input(scoped)


@pytest.mark.parametrize("kind,path", [
    ("metric", "unit"), ("metric", "period"), ("metric", "baseline"),
    ("metric", "result"), ("metric", "scope"), ("metric", "qualifiers"),
    ("technology", "display"), ("technology", "canonicalId"),
    ("leadership", "action"), ("leadership", "teamSize.unit"),
    ("leadership", "teamSize.period"), ("leadership", "teamSize.baseline"),
    ("leadership", "teamSize.result"), ("leadership", "teamSize.scope"),
    ("leadership", "teamSize.qualifiers"),
])
def test_contact_in_any_selected_free_text_value_preserves_fact_and_normal_checks(kind, path):
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    if kind == "metric":
        fact = next(item for item in sheet["facts"] if item["id"] == "recent_metric")
    elif kind == "technology":
        fact = {"id": "recent_technology", "revision": 1, "kind": "technology",
                "value": {"canonicalId": "python", "display": "Python", "scope": "job"},
                "evidence": [], "origin": "user", "importance": "essential",
                "jobId": "recent", "subprojectId": None}
        sheet["facts"].append(fact)
        sheet["employment"][0]["factIds"].append(fact["id"])
    else:
        fact = {"id": "recent_leadership", "revision": 1, "kind": "leadership",
                "value": {"action": "Led the team", "attribution": "personal", "teamSize": {
                    "number": 5, "upperNumber": None, "comparator": "exact", "unit": "engineers",
                    "period": None, "baseline": None, "result": None, "scope": None,
                    "attribution": "personal", "qualifiers": []}},
                "evidence": [], "origin": "user", "importance": "essential",
                "jobId": "recent", "subprojectId": None}
        sheet["facts"].append(fact)
        sheet["employment"][0]["factIds"].append(fact["id"])
    target = fact["value"] if "." not in path else fact["value"]["teamSize"]
    field = path.split(".")[-1]
    private = "contact me at 555-123-4567"
    target[field] = [private] if field == "qualifiers" else private
    scoped = request.model_copy(update={"sheet": FactSheet.model_validate(sheet)})
    payload = draft_input(scoped)
    assert private in payload and fact["id"] in payload
    selection = draft_selection(scoped)
    candidate = DraftProposal(blocks=[{"blockId": block_id, "text": "Safe draft text.",
                                      "factIds": [item.id for item in facts]}
                                     for block_id, facts in selection.items()])
    issues = validate_draft(scoped, candidate).issues
    assert all(fact["id"] in [item.id for item in facts] for facts in selection.values())
    assert not any("withheld" in issue.message for issue in issues)
    if kind in {"metric", "leadership"}:
        assert any(issue.code == "QUALIFIER_LOSS" and issue.fact_id == fact["id"] for issue in issues)


def test_mixed_achievement_contact_fact_keeps_job_and_required_coverage():
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    sheet["facts"] = [fact for fact in sheet["facts"] if fact["id"] not in {"recent_text", "recent_metric"}]
    mixed = {"id": "mixed_private", "revision": 1, "kind": "text",
             "value": {"text": "Built a service for 20 teams. Call 555-123-4567."},
             "evidence": [], "origin": "user", "importance": "essential",
             "jobId": "recent", "subprojectId": None}
    sheet["facts"].append(mixed)
    sheet["employment"][0]["factIds"] = [mixed["id"]]
    scoped = request.model_copy(update={"sheet": FactSheet.model_validate(sheet)})
    payload = draft_input(scoped)
    assert "mixed_private" in payload and "555-123-4567" in payload
    assert [block["blockId"] for block in json.loads(payload)["blocks"]] == ["profile", "prose_recent"]
    candidate = DraftProposal(blocks=[{"blockId": "profile", "text": "Designed reliable systems.",
                                       "factIds": ["global_strength"]},
                                      {"blockId": "prose_recent", "text": mixed["value"]["text"], "factIds": ["mixed_private"]}])
    issues = validate_draft(scoped, candidate).issues
    assert {(issue.code, issue.block_id, issue.fact_id) for issue in issues if issue.fact_id == "mixed_private"} == {
        ("MISSING_REQUIRED", "profile", "mixed_private")}
    assert all("555-123-4567" not in issue.message for issue in issues)


@pytest.mark.parametrize("private", ["Call 5551234567", "Portfolio: alice.dev",
                                      "Website: alice.com", "LinkedIn: linkedin.com"])
def test_all_candidate_contacts_reach_provider_without_content_rejection(tmp_path, private):
    class Provider:
        calls = 0

        def generate(self, call, files, cancel):
            self.calls += 1
            payload = json.loads(call.text)
            return ContentResult(value=DraftProposal(blocks=[{
                "blockId": block["blockId"], "text": "Contact details retained.",
                "factIds": [fact["id"] for fact in block["facts"]]} for block in payload["blocks"]]),
                usage=ReportedUsage(), cli_version="fixture", model="fixture",
                elapsed_seconds=0.01, logical_attempts=1)

    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    sheet["facts"] = [fact for fact in sheet["facts"] if fact["id"] != "global_strength"]
    next(fact for fact in sheet["facts"] if fact["id"] == "recent_text")["value"]["text"] = private
    next(fact for fact in sheet["facts"] if fact["id"] == "recent_metric")["value"]["scope"] = private
    scoped = request.model_copy(update={"sheet": FactSheet.model_validate(sheet)})
    provider = Provider()
    with OperationFiles(tmp_path).open() as files:
        result, _ = DraftingContentService(provider, "fixture").run(scoped, files, threading.Event())
    assert provider.calls == 1 and len(result.blocks) == 2
    assert next(fact for fact in scoped.sheet.facts if fact.id == "recent_text").value.text == private


def test_injected_provider_receives_contacts_and_result_keeps_normal_review(tmp_path):
    class Provider:
        calls = 0
        text = ""

        def generate(self, call, files, cancel):
            self.calls += 1
            self.text = call.text
            payload = json.loads(call.text)
            return ContentResult(value=DraftProposal(blocks=[{
                "blockId": block["blockId"], "text": "Safe draft text.",
                "factIds": [fact["id"] for fact in block["facts"]]} for block in payload["blocks"]]),
                usage=ReportedUsage(input_tokens=10, output_tokens=10), cli_version="fixture",
                model="fixture", elapsed_seconds=0.01, logical_attempts=1,
                internal_inference_count=None)

    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    next(fact for fact in sheet["facts"] if fact["id"] == "recent_metric")["value"]["scope"] = "contact me at 555-123-4567"
    sheet["facts"].append({"id": "mixed_private", "revision": 1, "kind": "text",
                           "value": {"text": "Built a service for 20 teams. Call 555-123-4567."},
                           "evidence": [], "origin": "user", "importance": "essential",
                           "jobId": "recent", "subprojectId": None})
    sheet["employment"][0]["factIds"].append("mixed_private")
    scoped = request.model_copy(update={"sheet": FactSheet.model_validate(sheet)})
    provider = Provider()
    with OperationFiles(tmp_path).open() as files:
        result, _ = DraftingContentService(provider, "fixture").run(scoped, files, threading.Event())
    assert provider.calls == 1
    assert "555-123-4567" in provider.text
    assert "recent_metric" in provider.text and "mixed_private" in provider.text
    assert any(issue.fact_id == "recent_metric" and issue.code == "QUALIFIER_LOSS" for issue in result.issues)
    assert any(issue.fact_id == "mixed_private" and issue.code == "SOURCE_REVIEW" for issue in result.issues)
    assert all("555-123-4567" not in issue.message for issue in result.issues)
    assert next(fact for fact in scoped.sheet.facts if fact.id == "recent_metric").value.scope == "contact me at 555-123-4567"


def test_global_metric_remains_in_profile_selection_and_required_ids():
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    metric = next(fact for fact in sheet["facts"] if fact["id"] == "recent_metric").copy()
    metric.update(id="global_metric", jobId=None, importance="normal")
    sheet["facts"].append(metric)
    scoped = request.model_copy(update={"sheet": FactSheet.model_validate(sheet)})
    profile = next(block for block in json.loads(draft_input(scoped))["blocks"] if block["blockId"] == "profile")
    assert "global_metric" in profile["requiredFactIds"]


def test_explicit_job_correction_is_required_and_old_source_value_is_excluded():
    request = request_with_jobs()
    sheet = request.sheet.model_dump(mode="json", by_alias=True)
    sheet["facts"].append({"id": "job_fix", "revision": 1, "kind": "text",
                           "value": {"text": "Corrected job work."}, "evidence": [], "origin": "user",
                           "importance": "normal", "jobId": "recent", "subprojectId": None})
    sheet["employment"][0]["factIds"].append("job_fix")
    sheet["facts"] = [{**fact, "origin": "source", "evidence": [{"sourceId": sheet["units"][0]["sourceId"],
        "sourceRevision": 1, "unitId": sheet["units"][0]["unitId"], "unitRevision": 1}]}
        if fact["id"] == "recent_text" else fact for fact in sheet["facts"]]
    sheet["units"][0]["factIds"].append("recent_text")
    sheet["units"][0]["disposition"] = "facts"
    sheet["userCorrections"] = {"recent_text": "job_fix"}
    scoped = request.model_copy(update={"sheet": FactSheet.model_validate(sheet)})
    prompt = json.loads(draft_input(scoped))
    job = next(block for block in prompt["blocks"] if block["blockId"] == "prose_recent")
    assert "job_fix" in job["requiredFactIds"]
    assert "recent_text" not in [fact["id"] for fact in job["facts"]]


def test_manual_profile_is_omitted_before_provider_when_explicit_content_must_remain():
    request = request_with_jobs().model_copy(update={"preserve_manual_profile": True})
    selected = draft_selection(request)
    assert "profile" not in selected
    assert "prose_recent" in selected
    assert [block["blockId"] for block in json.loads(draft_input(request))["blocks"]] == ["prose_recent"]


def test_number_preservation_uses_complete_numeric_tokens():
    request = request_with_jobs()
    candidate = proposal()
    candidate.blocks[1].text = "Built a service. team peak at most 5000 requests per day in the service."
    assert any(issue.code == "QUALIFIER_LOSS" for issue in validate_draft(request, candidate).issues)
    candidate.blocks[1].text = "Built a service. team peak at most -20 requests per day in the service."
    assert any(issue.code == "QUALIFIER_LOSS" for issue in validate_draft(request, candidate).issues)


def test_required_qualifiers_credit_and_references_are_reviewed():
    request = request_with_jobs()
    accepted = validate_draft(request, proposal())
    assert {(issue.code, issue.fact_id) for issue in accepted.issues} == {("MISSING_REQUIRED", "contact")}
    missing = proposal()
    missing.blocks[1].fact_ids.remove("recent_metric")
    assert any(issue.code == "MISSING_REQUIRED" for issue in validate_draft(request, missing).issues)
    lost = proposal()
    lost.blocks[1].text = "Built a service with 20 requests."
    assert {issue.code for issue in validate_draft(request, lost).issues if issue.fact_id == "recent_metric"} == {
        "QUALIFIER_LOSS", "ATTRIBUTION_LOSS"}
    broken = proposal()
    broken.blocks[1].fact_ids.append("contact")
    with pytest.raises(ValueError, match="reference"):
        validate_draft(request, broken)


def test_leadership_team_size_and_credit_loss_stay_visible():
    request = request_with_jobs()
    value = request.sheet.model_dump(mode="json", by_alias=True)
    value["facts"].append({"id": "leadership", "revision": 1, "kind": "leadership",
                           "value": {"action": "Built the team", "attribution": "personal", "teamSize": {
                               "number": 5, "upperNumber": None, "comparator": "exact", "unit": "engineers",
                               "period": None, "baseline": "zero", "result": None, "scope": None,
                               "attribution": "personal", "qualifiers": []}},
                           "evidence": [], "origin": "user", "importance": "essential",
                           "jobId": "recent", "subprojectId": None})
    value["employment"][0]["factIds"].append("leadership")
    request = request.model_copy(update={"sheet": FactSheet.model_validate(value)})
    candidate = proposal()
    for block in candidate.blocks:
        block.fact_ids.append("leadership")
        block.text += " Built the team with 5 engineers from zero, personal credit."
    assert {(issue.code, issue.fact_id) for issue in validate_draft(request, candidate).issues} == {
        ("MISSING_REQUIRED", "contact")}
    candidate.blocks[1].text = "Built the team with 5 engineers."
    issues = validate_draft(request, candidate).issues
    assert {issue.code for issue in issues if issue.fact_id == "leadership"} == {"QUALIFIER_LOSS", "ATTRIBUTION_LOSS"}


def test_one_scoped_provider_call_and_cancel_before_launch(tmp_path):
    class Provider:
        calls = 0
        text = ""

        def generate(self, call, files, cancel):
            self.calls += 1
            self.text = call.text
            return ContentResult(value=proposal(), usage=ReportedUsage(input_tokens=10, output_tokens=20),
                                 cli_version="fixture", model="fixture", elapsed_seconds=0.01,
                                 logical_attempts=1, internal_inference_count=None)

    provider = Provider()
    service = DraftingContentService(provider, "fixture")
    with OperationFiles(tmp_path).open() as files:
        result, usage = service.run(request_with_jobs(), files, threading.Event())
    assert len(result.blocks) == 2 and usage == {"logicalAttempts": 1, "inputTokens": 10,
                                                 "outputTokens": 20, "inferenceCount": None}
    assert provider.calls == 1 and "private@example.test" in provider.text
    cancel = threading.Event()
    cancel.set()
    with OperationFiles(tmp_path).open() as files, pytest.raises(InterruptedError):
        service.run(request_with_jobs(), files, cancel)
    assert provider.calls == 1
