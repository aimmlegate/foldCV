"""Candidate and observation behavior with frozen, controlled evidence."""

import copy
import json
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_normalization import GuiSemanticProposal, normalize_candidate, public_context_facts
from packages.resume_core.models.recovery import NameAssessmentFact, ObservationFact
from packages.resume_core.rules import captured_rules, DEFAULT_RULES
from resume_api.gui_normalization_content import GuiNormalizationContentService
from resume_api.lifecycle import OperationFiles
from resume_api.providers.content import ContentFailure, ContentResult, ReportedUsage
from tests.recovery.candidate_fixtures import ROOT, request, proposal, span, value

RULES = captured_rules(DEFAULT_RULES, 1)


class ControlledProvider:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def generate(self, content, _files, _cancel):
        self.calls.append(json.loads(content.text))
        assert content.policy.allow_repair is False
        assert content.result_type is GuiSemanticProposal
        return ContentResult(self.reply, ReportedUsage(), "fixture", content.policy.model, 0.1, 1)


@pytest.mark.parametrize("example", ["E1", "E2"])
def test_candidate_education_languages_match_independent_source_manifest(example, tmp_path):
    source_request = request((ROOT / f"{example}.txt").read_text())
    expected = json.loads((ROOT / "expected.json").read_text())["examples"][example]
    provider = ControlledProvider(proposal(source_request, example))
    service = GuiNormalizationContentService(provider, "fixture-model")
    result, usage = service.run(source_request, RULES, OperationFiles(tmp_path), threading.Event())
    assert len(provider.calls) == usage["logicalAttempts"] == 1
    assert result.candidate.name.text == expected["candidate"]["name"]
    assert result.candidate.title.text == expected["candidate"]["title"]
    assert result.source_observed_at is None
    assert provider.calls[0]["rulesUsed"]["revision"] == RULES.revision
    assert len(result.semantic_proposal.jobs) == len(expected["jobs"])
    if example == "E1":
        assert result.education[0].institution.text == expected["education"][0]["institution"]
        assert result.education[0].specialty.text == expected["education"][0]["specialty"]
        assert result.education[0].date_text.text == str(expected["education"][0]["year"])
        assert [(row.name.text, row.proficiency.text) for row in result.languages] == [
            (row["name"], row["proficiency"]) for row in expected["languages"]]
    else:
        assert result.name_assessment.missing_surname is None
        assert result.education == result.languages == []
    assert all(not unit.represented_fact_ids for unit in source_request.sources[0].units)
    for fact in result.facts:
        for evidence in fact.evidence:
            unit = next(unit for source in result.sources if source.id == evidence.source_id
                        for unit in source.units if unit.id == evidence.unit_id)
            assert fact.id in unit.represented_fact_ids
    assert any(isinstance(fact, NameAssessmentFact) for fact in result.facts)
    assert any(isinstance(fact, ObservationFact) for fact in result.facts)
    assert usage["inputTokens"] is None and usage["inferenceCount"] is None


@pytest.mark.parametrize("input_text,missing", [
    ("Имя: Алексей. Фамилия: не указана.", True), ("Имя: Алексей.", None),
    ("Имя: Мадонна. Единственное имя, фамилии нет.", False),
])
def test_name_assessments_use_evidence_without_single_token_guessing(input_text, missing):
    source_request = request((ROOT / "E2.txt").read_text() + input_text + "\n")
    raw = proposal(source_request, "E2").model_dump(by_alias=True)
    raw["nameAssessment"] = {"missingSurname": missing, "evidence": [span(source_request.sources[0], input_text)] if missing is not None else [], "revision": 999}
    result = normalize_candidate(source_request, GuiSemanticProposal.model_validate(raw), RULES)
    assert result.name_assessment.missing_surname is missing
    assert result.name_assessment.revision == source_request.revision


def test_observation_date_requires_dated_source_evidence_and_has_one_producer():
    text = (ROOT / "E1.txt").read_text() + "Резюме обновлено 10.10.2026\n"
    source_request = request(text)
    raw = proposal(source_request).model_dump(by_alias=True)
    observed = {"precision": "day", "year": 2026, "month": 10, "day": 10}
    raw["observationAssessment"] = {"sourceObservedAt": observed, "evidence": span(source_request.sources[0], "Резюме обновлено 10.10.2026"), "revision": 99}
    result = normalize_candidate(source_request, GuiSemanticProposal.model_validate(raw), RULES)
    assert result.source_observed_at.model_dump() == {"precision": "day", "year": 2026, "month": 10, "day": 10}
    assert result.observation_assessment.revision == 1
    assert result.source_observed_at != source_request.formatting_as_of
    assert next(fact for fact in result.facts if isinstance(fact, ObservationFact)).value.evidence.text == "Резюме обновлено 10.10.2026"


@pytest.mark.parametrize("change,code", [
    ("absent", "INVALID_SOURCE_EVIDENCE"), ("foreign", "INVALID_SOURCE_EVIDENCE"),
    ("future", "SOURCE_OBSERVATION_AFTER_FORMATTING_DATE"),
])
def test_invalid_observation_fails_one_attempt_without_repair_or_source_mutation(change, code, tmp_path):
    source_request = request((ROOT / "E1.txt").read_text() + "Резюме обновлено 10.10.2026\n")
    raw = proposal(source_request).model_dump(by_alias=True)
    evidence = span(source_request.sources[0], "Резюме обновлено 10.10.2026")
    if change == "absent": evidence["text"] = "missing private source marker"
    if change == "foreign": evidence["unitId"] = "foreign unit"
    observed = {"precision": "day", "year": 2027 if change == "future" else 2026, "month": 10, "day": 10}
    raw["observationAssessment"] = {"sourceObservedAt": observed, "evidence": evidence, "revision": 1}
    provider = ControlledProvider(GuiSemanticProposal.model_validate(raw))
    with pytest.raises(ContentFailure) as error:
        GuiNormalizationContentService(provider, "fixture").run(source_request, RULES, OperationFiles(tmp_path), threading.Event())
    assert error.value.code == code and error.value.logical_attempts == 1
    assert len(provider.calls) == 1
    assert "private source marker" not in str(error.value)
    assert all(not unit.represented_fact_ids for unit in source_request.sources[0].units)


def test_candidate_details_keep_evidence_and_remain_in_content_context():
    text = (ROOT / "E1.txt").read_text() + "Email: fictional@example.invalid\nPhone: +12345678901\nAge: 42\nJob board: synthetic\n"
    source_request = request(text)
    raw = proposal(source_request).model_dump(by_alias=True)
    private = [("email", "fictional@example.invalid"), ("phone", "+12345678901"), ("age", "42"), ("platform_metadata", "Job board: synthetic")]
    raw["privateDetails"] = [{"kind": kind, "value": value(source_request.sources[0], literal)} for kind, literal in private]
    result = normalize_candidate(source_request, GuiSemanticProposal.model_validate(raw), RULES)
    assert [(item.kind, item.value.text) for item in result.private_details] == private
    public = public_context_facts(result.facts)
    assert all(any(fact.value.text == literal for fact in public) for _, literal in private)
    assert any(fact.value.field == "private_metadata" for fact in public)
    authored = json.dumps(result.candidate.model_dump(by_alias=True))
    assert "fictional@example.invalid" not in authored
    assert any(fact.kind == "candidate_detail" and fact.value.field == "private_metadata" for fact in result.facts)


def test_candidate_invention_and_unsupported_name_assessment_fail():
    from packages.resume_core.gui_normalization import NormalizationFailure

    source_request = request((ROOT / "E2.txt").read_text())
    raw = proposal(source_request, "E2").model_dump(by_alias=True)
    raw["candidate"]["name"]["text"] = "Алексей Выдуманный"
    with pytest.raises(NormalizationFailure, match="UNSUPPORTED_CANDIDATE_VALUE"):
        normalize_candidate(source_request, GuiSemanticProposal.model_validate(raw), RULES)
    raw = proposal(source_request, "E2").model_dump(by_alias=True)
    raw["nameAssessment"]["missingSurname"] = True
    with pytest.raises(NormalizationFailure, match="NAME_ASSESSMENT_NEEDS_EVIDENCE"):
        normalize_candidate(source_request, GuiSemanticProposal.model_validate(raw), RULES)


def test_source_unit_ids_are_unique_across_files_and_replacement_identity_is_preserved():
    from packages.resume_core.extraction.parser import extract
    from packages.resume_core.gui_normalization import canonical_source

    first = canonical_source(extract(b"One", "one.txt"))
    second = canonical_source(extract(b"Two", "two.txt"))
    assert first.units[0].id != second.units[0].id
    replacement = canonical_source(extract(b"One", "one.txt"), source_id="replacement-id")
    assert replacement.id == "replacement-id" and replacement.units[0].id.startswith("replacement-id/")
    assert replacement.byte_sha256 == first.byte_sha256
