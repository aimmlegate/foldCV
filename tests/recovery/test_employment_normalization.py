"""Employment scope, explicit dates and preserved literal conflicting claims."""

import copy
import json
from pathlib import Path
import threading
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_normalization import GuiSemanticProposal, normalize_candidate
from packages.resume_core.gui_employment import normalize_employment
from packages.resume_core.models.recovery import GuiLeadershipFact, GuiTechnologyFact, GuiMetricFact
from packages.resume_core.rules import DEFAULT_RULES, captured_rules
from packages.resume_core.normalization import _observed_number
from resume_api.gui_normalization_content import GuiNormalizationContentService
from resume_api.lifecycle import OperationFiles
from tests.recovery.candidate_fixtures import ROOT, request, span
from tests.recovery.employment_fixtures import employment_proposal
from tests.recovery.test_candidate_normalization import ControlledProvider
from tests.support.recovery import assert_e2_claims

RULES = captured_rules(DEFAULT_RULES, 1)


def result_for(example):
    source = request((ROOT / f"{example}.txt").read_text())
    reply = employment_proposal(source, example)
    return source, reply, normalize_employment(source, reply, normalize_candidate(source, reply, RULES))


@pytest.mark.parametrize("example", ["E1", "E2"])
def test_employment_jobs_scope_precision_and_credit_match_independent_manifest(example, tmp_path):
    source = request((ROOT / f"{example}.txt").read_text())
    reply = employment_proposal(source, example)
    provider = ControlledProvider(reply)
    result, usage = GuiNormalizationContentService(provider, "fixture").run(source, RULES, OperationFiles(tmp_path), threading.Event())
    expected = json.loads((ROOT / "expected.json").read_text())["examples"][example]
    assert len(provider.calls) == usage["logicalAttempts"] == 1
    assert [job.employer for job in result.employment] == [job["employer"] for job in expected["jobs"]]
    technologies = [fact for fact in result.facts if isinstance(fact, GuiTechnologyFact)]
    global_facts = [fact for fact in technologies if fact.value.scope == "global"]
    assert [fact.value.display for fact in global_facts] == expected["globalTechnologies"]
    assert all(fact.job_id is None and fact.subproject_id is None for fact in global_facts)
    assert all(period.start.precision == "year" for job in result.employment for period in job.periods)
    assert result.source_observed_at is None
    if example == "E1":
        metric = next(fact for fact in result.facts if isinstance(fact, GuiMetricFact))
        assert metric.value.number == 70 and metric.value.baseline == "100" and metric.value.result == "70"
        assert metric.value.unit == "мс" and metric.value.attribution == "team" and metric.value.qualifiers == ["на 30%"]
        trainee = next(fact for fact in result.facts if isinstance(fact, GuiLeadershipFact))
        assert trainee.value.team_size.number == 2 and trainee.value.attribution == "personal"
        north = result.employment[0]
        assert result.job_periods[north.id][0].present is True
    else:
        gamma = result.employment[0]
        assert gamma.periods == [] and result.job_periods[gamma.id] == []
        assert next(fact for fact in technologies if fact.value.display == "ExampleDB-X").value.canonical_id.startswith("unknown_")
        assert len(result.conflicts) == 1 and len(result.conflicts[0].fact_ids) == 2
    for job in result.employment:
        assert set(job.fact_ids) == {fact.id for fact in result.facts if fact.job_id == job.id}


def test_e2_literal_claim_span_oracle_keeps_both_claims_without_numeral_parser():
    source, reply, result = result_for("E2")
    claims = [fact for fact in result.facts if isinstance(fact, GuiLeadershipFact)]
    assert [(fact.literal_evidence[0].text, fact.value.team_size.number) for fact in claims] == [("пять", 5), ("шесть", 6)]
    assert len({fact.id for fact in claims}) == 2
    assert set(result.conflicts[0].fact_ids) == {fact.id for fact in claims}
    assert all(fact.value.attribution == "unknown" and fact.value.action == "Размер команды" for fact in claims)
    # The frozen oracle uses symbolic IDs; actual canonical unit/source checks happen in the merge.
    oracle = [{"factId": item.temp_id, "jobId": item.job_temp_id, "unitId": "E2-unit",
               "span": item.literal_evidence[0].text, "teamSize": item.value.team_size.number,
               "candidateLedTeam": False} for item in reply.facts if item.kind == "leadership"]
    assert_e2_claims(oracle)
    wrong = copy.deepcopy(oracle)
    wrong[0]["teamSize"] = 6
    with pytest.raises(AssertionError, match="frozen oracle"):
        assert_e2_claims(wrong)
    assert _observed_number(5, "пять") is False


@pytest.mark.parametrize("change,code", [
    ("foreign", "INVALID_SOURCE_EVIDENCE"), ("job", "FACT_OUTSIDE_JOB"),
    ("global", "TECHNOLOGY_SCOPE_MISMATCH"), ("qualifier", "UNSUPPORTED_METRIC_QUALIFIER"),
    ("accounting", "INCOMPLETE_UNIT_ACCOUNTING"),
])
def test_employment_invalid_evidence_scope_qualifier_and_accounting_fail(change, code):
    from packages.resume_core.gui_normalization import NormalizationFailure

    source = request((ROOT / "E1.txt").read_text())
    raw = employment_proposal(source).model_dump(by_alias=True)
    if change == "foreign": raw["facts"][0]["literalEvidence"][0]["sourceId"] = "foreign"
    if change == "job": raw["facts"][0]["jobTempId"] = "west"
    if change == "global": raw["facts"][0]["value"]["scope"] = "global"
    if change == "qualifier": next(fact for fact in raw["facts"] if fact["kind"] == "metric")["value"]["qualifiers"] = ["up to"]
    if change == "accounting": raw["units"].pop()
    reply = GuiSemanticProposal.model_validate(raw)
    candidate = normalize_candidate(source, reply, RULES)
    with pytest.raises(NormalizationFailure, match=code):
        normalize_employment(source, reply, candidate)
    assert candidate.employment == []


def test_start_only_is_not_present_and_never_creates_a_complete_projection():
    source = request((ROOT / "E1.txt").read_text())
    raw = employment_proposal(source).model_dump(by_alias=True)
    raw["jobs"][0]["periods"][0]["present"] = False
    reply = GuiSemanticProposal.model_validate(raw)
    result = normalize_employment(source, reply, normalize_candidate(source, reply, RULES))
    north = result.employment[0]
    assert north.periods == []
    assert result.job_periods[north.id][0].start_text == "2021"
    assert result.job_periods[north.id][0].end_text == ""
    assert result.job_periods[north.id][0].present is False


def test_subproject_keeps_full_record_and_owned_fact_mapping():
    source = request((ROOT / "E1.txt").read_text() + "Север: Подсистема 2021–2022. Python.\n")
    raw = employment_proposal(source).model_dump(by_alias=True)
    evidence = span(source.sources[0], "Подсистема")
    unit = evidence["unitId"]
    raw["jobs"][0]["unitIds"].append(unit)
    year = lambda number: {"precision": "year", "year": number, "month": None, "day": None}
    raw["jobs"][0]["subprojects"] = [{"tempId": "sub", "name": "Подсистема", "period": {"start": year(2021), "end": year(2022)}, "unitIds": [unit]}]
    evidence = span(source.sources[0], "Python")
    evidence["unitId"] = unit
    raw["facts"].append({"tempId": "sub-python", "kind": "technology", "value": {"canonicalId": "python", "display": "Python", "scope": "subproject"},
                         "sourceId": source.sources[0].id, "unitIds": [unit], "jobTempId": "north", "subprojectTempId": "sub", "literalEvidence": [evidence]})
    next(account for account in raw["units"] if account["unitId"] == unit)["factTempIds"] = ["sub-python"]
    reply = GuiSemanticProposal.model_validate(raw)
    result = normalize_employment(source, reply, normalize_candidate(source, reply, RULES))
    sub = result.employment[0].subprojects[0]
    assert sub.name == "Подсистема" and sub.period.start.year == 2021 and sub.period.end.year == 2022
    fact = next(fact for fact in result.facts if fact.subproject_id == sub.id)
    assert sub.fact_ids == [fact.id] and fact.job_id == result.employment[0].id


def test_gui_digit_team_size_retains_existing_numeric_guard():
    from packages.resume_core.gui_normalization import NormalizationFailure

    source = request((ROOT / "E2.txt").read_text() + "Гамма: команда 5 человек.\n")
    raw = employment_proposal(source, "E2").model_dump(by_alias=True)
    claim = next(fact for fact in raw["facts"] if fact["tempId"] == "gamma-team-five")
    evidence = span(source.sources[0], "команда 5 человек")
    claim["literalEvidence"] = [evidence]
    claim["unitIds"] = [evidence["unitId"]]
    claim["value"]["teamSize"]["number"] = 6
    raw["jobs"][0]["unitIds"].append(evidence["unitId"])
    reply = GuiSemanticProposal.model_validate(raw)
    with pytest.raises(NormalizationFailure, match="UNSUPPORTED_TEAM_SIZE"):
        normalize_employment(source, reply, normalize_candidate(source, reply, RULES))


def test_normalized_headers_and_field_addresses_are_retained_in_canonical_facts():
    from packages.resume_core.models.recovery import EmploymentFact, CandidateFact

    _source, _reply, result = result_for("E1")
    headers = [fact for fact in result.facts if isinstance(fact, EmploymentFact)]
    assert {fact.value.job_id for fact in headers} == {job.id for job in result.employment}
    assert headers[0].value.periods[0].present is True
    assert all(fact.value.field_id for fact in result.facts if isinstance(fact, CandidateFact))
    assert headers[0].literal_evidence
