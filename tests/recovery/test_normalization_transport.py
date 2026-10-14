"""Compact native references keep canonical grounding and every source unit."""

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_normalization import GuiSemanticProposal, NormalizationFailure, normalize_candidate, normalization_input
from packages.resume_core.gui_employment import normalize_employment
from resume_api.gui_normalization_transport import NormalizationTransport
from tests.recovery.candidate_fixtures import ROOT, request
from tests.recovery.employment_fixtures import employment_proposal
from tests.recovery.test_employment_normalization import RULES


def source(example="E1"):
    return request((ROOT / (example + ".txt")).read_text())


def test_compact_prompt_preserves_all_text_revisions_order_and_rules():
    captured = source()
    before = captured.model_dump(mode="json", by_alias=True)
    compact = NormalizationTransport(captured).prompt(RULES)
    payload = json.loads(compact)
    assert payload["rulesUsed"] == RULES.model_dump(mode="json", by_alias=True)
    assert payload["input"]["revision"] == captured.revision
    rows = payload["input"]["sources"]
    assert rows[0]["id"] == "s0" and rows[0]["revision"] == captured.sources[0].revision
    assert [row["text"] for row in rows[0]["units"]] == [unit.text for unit in captured.sources[0].units]
    assert [row["revision"] for row in rows[0]["units"]] == [unit.revision for unit in captured.sources[0].units]
    assert set(rows[0]) == {"id", "revision", "units"}
    assert len(compact.encode()) < len(normalization_input(captured, RULES).encode())
    assert captured.model_dump(mode="json", by_alias=True) == before


@pytest.mark.parametrize("example", ["E1", "E2"])
def test_sparse_accounting_restores_canonical_jobs_facts_and_every_unit(example):
    captured = source(example)
    full = employment_proposal(captured, example)
    raw = full.model_dump(by_alias=True)
    raw["units"] = []
    transport = NormalizationTransport(captured)
    reply = transport.restore(GuiSemanticProposal.model_validate(raw))
    expected = normalize_employment(captured, full, normalize_candidate(captured, full, RULES))
    actual = normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert actual.facts == expected.facts and actual.employment == expected.employment
    assert actual.job_periods == expected.job_periods and actual.conflicts == expected.conflicts
    assert actual.sources == expected.sources
    assert len(reply.units) == sum(len(value.units) for value in captured.sources)
    assert all(unit.disposition == "unresolved" for unit in reply.units if not unit.fact_temp_ids)
    assert raw["units"] == []


def test_short_evidence_references_restore_without_rewriting_literal_values():
    captured = source()
    full = employment_proposal(captured)
    raw = full.model_dump(by_alias=True)
    first = raw["facts"][0]
    original_span = deepcopy(first["literalEvidence"][0])
    transport = NormalizationTransport(captured)
    alias = transport.unit_aliases[(original_span["sourceId"], original_span["unitId"])]
    first["sourceId"] = "s0"
    first["unitIds"] = [alias]
    first["literalEvidence"][0]["sourceId"] = "s0"
    first["literalEvidence"][0]["unitId"] = alias
    reply = transport.restore(GuiSemanticProposal.model_validate(raw))
    assert reply.facts[0] == full.facts[0]
    assert reply.facts[0].literal_evidence[0].text == original_span["text"]
    normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))


@pytest.mark.parametrize("change,code", [("foreign", "INVALID_SOURCE_EVIDENCE"),
    ("revision", "INVALID_SOURCE_EVIDENCE"), ("invented", "INVALID_SOURCE_EVIDENCE"),
    ("duplicate", "INCOMPLETE_UNIT_ACCOUNTING"), ("mismatch", "UNIT_FACT_COVERAGE_MISMATCH")])
def test_transport_preserves_rejection_of_invalid_or_explicitly_wrong_evidence(change, code):
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    if change == "foreign": raw["facts"][0]["literalEvidence"][0]["unitId"] = "foreign"
    if change == "revision": raw["facts"][0]["literalEvidence"][0]["unitRevision"] += 1
    if change == "invented": next(row for row in raw["facts"] if row["kind"] == "text")["literalEvidence"][0]["text"] = "Unsupported claim"
    if change == "duplicate": raw["units"].append(deepcopy(raw["units"][0]))
    if change == "mismatch": next(row for row in raw["units"] if row["factTempIds"])["factTempIds"] = []
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    with pytest.raises(NormalizationFailure) as error:
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert error.value.code == code


def test_aliases_do_not_collide_with_original_identifiers():
    captured = source()
    original_source = captured.sources[0]
    original_source.id = "s0"
    original_source.units[0].id = "u0"
    transport = NormalizationTransport(captured)
    payload = json.loads(transport.prompt(RULES))["input"]["sources"][0]
    assert payload["id"] != "s0" and payload["units"][0]["id"] != "u0"
    assert transport.sources[payload["id"]] == "s0" and transport.units[payload["units"][0]["id"]] == "u0"


@pytest.mark.parametrize("separator", ["\n", "\u00a0", "\t", "  "])
def test_wrapped_supported_name_keeps_literal_evidence_and_display_value(separator):
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    wrapped = "Ирина" + separator + "Примерова"
    unit = next(unit for unit in captured.sources[0].units if "Ирина Примерова" in unit.text)
    unit.text = unit.text.replace("Ирина Примерова", wrapped)
    for row in [raw["candidate"]["name"], raw["nameAssessment"]]:
        for span in row["evidence"]:
            span["text"] = span["text"].replace("Ирина Примерова", wrapped)
    reply = GuiSemanticProposal.model_validate(raw)
    normalized = normalize_candidate(captured, reply, RULES)
    assert normalized.candidate.name.text == "Ирина Примерова"
    assert normalized.candidate.name.evidence[0].text == wrapped
    assert captured.sources[0].units[0].text == unit.text
    raw["candidate"]["name"]["text"] = "Примерова Ирина"
    with pytest.raises(NormalizationFailure) as error:
        normalize_candidate(captured, GuiSemanticProposal.model_validate(raw), RULES)
    assert error.value.code == "UNSUPPORTED_CANDIDATE_VALUE"


def test_explicit_present_endpoint_becomes_the_canonical_present_flag():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    raw["jobs"][0]["periods"][0]["endText"] = "настоящее время"
    reply = GuiSemanticProposal.model_validate(raw)
    actual = normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    period = actual.job_periods[actual.employment[0].id][0]
    assert period.present and period.end is None and period.end_text == ""
    assert "настоящее время" in period.evidence[0].text


def test_missing_end_date_does_not_support_a_present_assertion():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    raw["jobs"][1]["periods"][0].update(present=True, end=None, endText=None)
    reply = GuiSemanticProposal.model_validate(raw)
    with pytest.raises(NormalizationFailure) as error:
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert error.value.code == "INVALID_PRESENT_PERIOD"


@pytest.mark.parametrize("endpoint", ["not current", "no longer ongoing", "не настоящее время", "не по настоящее время"])
def test_negated_source_endpoint_cannot_assert_a_present_period(endpoint):
    text = (ROOT / "E1.txt").read_text().replace("настоящее время", endpoint)
    captured = request(text)
    raw = employment_proposal(captured).model_dump(by_alias=True)
    raw["jobs"][0]["periods"][0]["endText"] = endpoint
    reply = GuiSemanticProposal.model_validate(raw)
    with pytest.raises(NormalizationFailure) as error:
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert error.value.code == "INVALID_PRESENT_PERIOD"


def test_present_endpoint_keeps_unrelated_negated_claim_in_same_evidence():
    text = (ROOT / "E1.txt").read_text().replace("настоящее время.", "настоящее время. No current production incidents.")
    captured = request(text)
    raw = employment_proposal(captured).model_dump(by_alias=True)
    raw["jobs"][0]["periods"][0]["endText"] = "настоящее время"
    reply = GuiSemanticProposal.model_validate(raw)
    result = normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert result.job_periods[result.employment[0].id][0].present


def test_wrapped_subproject_and_text_claim_preserve_words_and_exact_evidence():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    text = "Сервис обработки заказов."
    wrapped = "Сервис\nобработки заказов."
    unit = next(unit for unit in captured.sources[0].units if text in unit.text)
    unit.text = unit.text.replace(text, wrapped)
    fact = next(fact for fact in raw["facts"] if fact["kind"] == "text" and fact["value"]["text"] == text)
    fact["literalEvidence"][0]["text"] = wrapped
    raw["jobs"][0]["subprojects"] = [{"tempId": "sub", "name": text, "period": None, "unitIds": [unit.id]}]
    reply = GuiSemanticProposal.model_validate(raw)
    result = normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert result.employment[0].subprojects[0].name == text
    assert any(item.kind == "text" and item.literal_evidence[0].text == wrapped for item in result.facts)
    raw["jobs"][0]["subprojects"][0]["name"] = "Неподтверждённый проект"
    with pytest.raises(NormalizationFailure) as error:
        reply = GuiSemanticProposal.model_validate(raw)
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert error.value.code == "UNSUPPORTED_SUBPROJECT_LITERAL"


def test_normalized_quote_spacing_recovers_only_the_exact_cited_source_literal():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    text = "Ирина Примерова"
    unit = next(unit for unit in captured.sources[0].units if text in unit.text)
    unit.text = unit.text.replace(text, "Ирина\nПримерова")
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    assert reply.candidate.name.evidence[0].text == "Ирина\nПримерова"
    normalize_candidate(captured, reply, RULES)
    raw["candidate"]["name"]["evidence"][0]["text"] = "Ирина Другая"
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    with pytest.raises(NormalizationFailure) as error:
        normalize_candidate(captured, reply, RULES)
    assert error.value.code == "INVALID_SOURCE_EVIDENCE"


def test_ambiguous_normalized_quote_cannot_choose_a_source_occurrence():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    unit = next(unit for unit in captured.sources[0].units if "Ирина Примерова" in unit.text)
    unit.text = "Ирина\nПримерова; Ирина\tПримерова"
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    with pytest.raises(NormalizationFailure) as error:
        normalize_candidate(captured, reply, RULES)
    assert error.value.code == "INVALID_SOURCE_EVIDENCE"


def test_unsupported_numeric_interpretation_keeps_only_the_verified_literal_claim():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    metric = next(row for row in raw["facts"] if row["kind"] == "metric")
    metric["value"]["number"] = 999999
    literal = "\n".join(span["text"] for span in metric["literalEvidence"])
    transport = NormalizationTransport(captured)
    reply = transport.restore(GuiSemanticProposal.model_validate(raw))
    kept = next(row for row in reply.facts if row.temp_id == metric["tempId"])
    assert kept.kind == "text" and kept.value.text == literal
    assert transport.unparsed_metrics == 1
    normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    metric["literalEvidence"][0]["text"] = "An invented source claim"
    reply = transport.restore(GuiSemanticProposal.model_validate(raw))
    assert next(row for row in reply.facts if row.temp_id == metric["tempId"]).kind == "metric"
    with pytest.raises(NormalizationFailure) as error:
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert error.value.code == "INVALID_SOURCE_EVIDENCE"


def test_fact_unit_bookkeeping_uses_verified_spans_without_widening_job_scope():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    fact = raw["facts"][0]
    other = next(unit.id for unit in captured.sources[0].units if unit.id not in fact["unitIds"])
    fact["unitIds"] = [other]
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    assert reply.facts[0].unit_ids == list(dict.fromkeys(span["unitId"] for span in fact["literalEvidence"]))
    normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    raw["jobs"][0]["unitIds"] = [other]
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    with pytest.raises(NormalizationFailure):
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))


def test_unknown_duplicate_target_keeps_unit_unresolved_instead_of_inventing_a_target():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    unit = next(row for row in raw["units"] if not row["factTempIds"])
    unit.update(disposition="duplicate", duplicateOf="unknown")
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    kept = next(row for row in reply.units if row.unit_id == unit["unitId"])
    assert kept.disposition == "unresolved" and kept.duplicate_of is None
    result = normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert sum(len(source.units) for source in result.sources) == sum(len(source.units) for source in captured.sources)


def test_candidate_value_cannot_stitch_words_across_separate_cited_spans():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    name, title = raw["candidate"]["name"], raw["candidate"]["title"]
    name["text"] += " " + title["text"]
    name["evidence"].extend(title["evidence"])
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    with pytest.raises(NormalizationFailure) as error:
        normalize_candidate(captured, reply, RULES)
    assert error.value.code == "UNSUPPORTED_CANDIDATE_VALUE"


def test_native_text_value_keeps_verified_quote_instead_of_unsupported_paraphrase():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    text = next(row for row in raw["facts"] if row["kind"] == "text")
    text["value"]["text"] = "An unsupported model assertion"
    with pytest.raises(NormalizationFailure) as error:
        direct = GuiSemanticProposal.model_validate(raw)
        normalize_employment(captured, direct, normalize_candidate(captured, direct, RULES))
    assert error.value.code == "UNSUPPORTED_FACT_TEXT"
    restored = NormalizationTransport(captured).restore(direct)
    kept = next(row for row in restored.facts if row.temp_id == text["tempId"])
    assert kept.value.text == "\n".join(span["text"] for span in text["literalEvidence"])
    normalize_employment(captured, restored, normalize_candidate(captured, restored, RULES))


def test_wrapped_metric_qualifier_keeps_exact_source_text_when_typed_value_is_unsupported():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    metric = next(row for row in raw["facts"] if row["kind"] == "metric")
    span = metric["literalEvidence"][0]
    span["text"] = span["text"].replace("на 30%", "на\n30%")
    unit = next(unit for unit in captured.sources[0].units if unit.id == span["unitId"])
    unit.text = unit.text.replace("на 30%", "на\n30%")
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    kept = next(row for row in reply.facts if row.temp_id == metric["tempId"])
    assert kept.kind == "text" and kept.value.text == span["text"]
    normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))


def test_subproject_accounting_cannot_expand_the_declared_job_boundary():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    job = raw["jobs"][0]
    owned = next(row for row in raw["facts"] if row["jobTempId"] == job["tempId"] and row["kind"] == "text")
    job["subprojects"] = [{"tempId": "sub", "name": job["employer"], "unitIds": [job["unitIds"][0]], "period": None}]
    owned["subprojectTempId"] = "sub"
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    assert set(owned["unitIds"]) <= set(reply.jobs[0].subprojects[0].unit_ids)
    foreign = next(row for row in raw["facts"] if row["jobTempId"] not in {None, job["tempId"]})
    owned.update(sourceId=foreign["sourceId"], unitIds=foreign["unitIds"], literalEvidence=foreign["literalEvidence"])
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    assert not set(foreign["unitIds"]) <= set(reply.jobs[0].subprojects[0].unit_ids)
    with pytest.raises(NormalizationFailure) as error:
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert error.value.code in {"FACT_OUTSIDE_JOB", "UNSUPPORTED_SUBPROJECT_LITERAL"}


def test_unowned_technology_stays_global_and_never_acquires_job_duration():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    skill = next(row for row in raw["facts"] if row["kind"] == "technology" and row["jobTempId"] is None)
    skill["value"]["scope"] = "job"
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    kept = next(row for row in reply.facts if row.temp_id == skill["tempId"])
    assert kept.value.scope == "global" and kept.job_temp_id is None
    normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))


@pytest.mark.parametrize("change", [None, "gap", "page", "partial", "reversed"])
def test_pdf_continuation_needs_complete_consecutive_units_on_one_page(change):
    from packages.resume_core.gui_normalization import EvidenceSpan, supported_text

    captured = source()
    document = captured.sources[0]
    first = document.units[0].model_copy(deep=True)
    second = first.model_copy(deep=True)
    first.text, second.text = "Study of distributed\n", "systems\n"
    first.order, second.order = 0, 1
    second.id += "-continuation"
    for unit in (first, second):
        unit.location.kind, unit.location.index = "page", 0
    document.units = [first, second]
    spans = [EvidenceSpan(sourceId=document.id, sourceRevision=document.revision,
        unitId=unit.id, unitRevision=unit.revision, text=unit.text.strip()) for unit in document.units]
    if change == "gap": second.order = 2
    if change == "page": second.location.index = 1
    if change == "partial": first.text = "Other heading: " + first.text
    if change == "reversed": spans.reverse()
    assert supported_text("Study of distributed systems", spans, [document]) is (change is None)


@pytest.mark.parametrize("change", [None, "gap", "page", "partial", "revision", "ambiguous"])
def test_missing_pdf_continuation_citation_requires_unique_literal_source_match(change):
    from packages.resume_core.gui_normalization import EvidenceSpan

    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    document = captured.sources[0]
    first = document.units[0].model_copy(deep=True)
    second = first.model_copy(deep=True)
    first.text, second.text = "Study of distributed\n", "systems\n"
    first.order, second.order = 0, 1
    second.id += "-continuation"
    for unit in (first, second):
        unit.location.kind, unit.location.index = "page", 0
    document.units = [first, second]
    span = EvidenceSpan(sourceId=document.id, sourceRevision=document.revision,
        unitId=first.id, unitRevision=first.revision, text=first.text.strip())
    raw["candidate"]["name"] = {"text": "Study of distributed systems", "evidence": [span.model_dump(by_alias=True)]}
    if change == "gap": second.order = 2
    if change == "page": second.location.index = 1
    if change == "partial": first.text = "Other heading: " + first.text
    if change == "revision": raw["candidate"]["name"]["evidence"][0]["unitRevision"] += 1
    if change == "ambiguous": second.text += "Study of distributed systems\n"
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    assert len(reply.candidate.name.evidence) == (2 if change is None else 1)
    if change is None:
        assert reply.candidate.name.evidence[1].text == second.text
        assert reply.candidate.name.text == "Study of distributed systems"


def test_technology_name_cannot_stitch_two_different_quoted_tools():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    python = next(row for row in raw["facts"] if row["tempId"] == "python")
    postgres = next(row for row in raw["facts"] if row["tempId"] == "postgres")
    python["value"]["display"] = "Python PostgreSQL"
    python["literalEvidence"].extend(postgres["literalEvidence"])
    python["unitIds"].extend(postgres["unitIds"])
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    with pytest.raises(NormalizationFailure) as error:
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert error.value.code == "UNSUPPORTED_TECHNOLOGY_LITERAL"


@pytest.mark.parametrize("change", [None, "foreign", "invalid"])
def test_conflicting_technology_scope_keeps_literal_text_without_inferred_duration(change):
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    fact = next(row for row in raw["facts"] if row["tempId"] == "python")
    fact["value"]["scope"] = "global"
    if change == "foreign": fact["jobTempId"] = "west"
    if change == "invalid": fact["literalEvidence"][0]["text"] = "Invented tool"
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    kept = next(row for row in reply.facts if row.temp_id == fact["tempId"])
    if change == "invalid":
        assert kept.kind == "technology"
    else:
        assert kept.kind == "text" and kept.value.text == "Python"
        assert kept.job_temp_id == fact["jobTempId"]
    if change is None:
        result = normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
        assert any(row.kind == "text" and row.value.text == "Python" for row in result.facts)
    else:
        with pytest.raises(NormalizationFailure) as error:
            normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
        assert error.value.code == ("FACT_OUTSIDE_JOB" if change == "foreign" else "INVALID_SOURCE_EVIDENCE")


@pytest.mark.parametrize("change", [None, "gap", "page"])
def test_employment_header_wrap_requires_declared_consecutive_pdf_units(change):
    from packages.resume_core.gui_employment import _supported_header

    captured = source()
    document = captured.sources[0]
    first = document.units[0].model_copy(deep=True)
    second = first.model_copy(deep=True)
    first.text, second.text = "Example\n", "Company\n"
    first.order, second.order = 0, 1
    second.id += "-continuation"
    for unit in (first, second): unit.location.kind, unit.location.index = "page", 0
    document.units = [first, second]
    if change == "gap": second.order = 2
    if change == "page": second.location.index = 1
    assert _supported_header("Example Company", document.id, [first.id, second.id], [document]) is (change is None)
    assert not _supported_header("Example Company", document.id, [first.id], [document])


@pytest.mark.parametrize("change", [None, "unsupported", "invalid"])
def test_unusable_source_observation_stays_unknown_without_changing_source_dates(change):
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    unit = captured.sources[0].units[0]
    unit.text += "\nSource updated 2027-01-02"
    span = {"sourceId": captured.sources[0].id, "sourceRevision": captured.sources[0].revision,
        "unitId": unit.id, "unitRevision": unit.revision, "text": "Source updated 2027-01-02"}
    date = {"precision": "day", "year": 2027, "month": 1, "day": 2}
    if change == "unsupported": date.update(year=2025)
    if change == "invalid": span["unitRevision"] += 1
    raw["observationAssessment"].update(sourceObservedAt=date, evidence=span)
    before = captured.model_dump(mode="json", by_alias=True)
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    if change == "invalid":
        assert reply.observation_assessment.source_observed_at is not None
        with pytest.raises(NormalizationFailure) as error:
            normalize_candidate(captured, reply, RULES)
        assert error.value.code == "INVALID_SOURCE_EVIDENCE"
    else:
        assert reply.observation_assessment.source_observed_at is None
        assert reply.observation_assessment.evidence is None
        result = normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
        assert result.source_observed_at is None
    assert captured.model_dump(mode="json", by_alias=True) == before


@pytest.mark.parametrize("collection,keys", [("education", ("institution", "qualification", "specialty", "dateText")),
    ("certifications", ("name", "issuer", "dateText")), ("languages", ("name", "proficiency"))])
def test_empty_native_detail_placeholder_is_an_empty_list_without_losing_evidence(collection, keys):
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    row = {"id": "unknown-row", **{key: {"text": "", "evidence": []} for key in keys}}
    original = deepcopy(raw[collection])
    raw[collection].append(row)
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    assert reply.model_dump(by_alias=True)[collection] == original
    normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    row[keys[0]]["evidence"] = raw["candidate"]["name"]["evidence"]
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    assert len(getattr(reply, collection)) == len(original) + 1
    with pytest.raises(NormalizationFailure) as error:
        normalize_candidate(captured, reply, RULES)
    assert error.value.code == "EMPTY_DETAIL_ROW"


@pytest.mark.parametrize("endpoint", ["по настоящее время (5 лет)", "настоящее время — 5 лет"])
def test_present_endpoint_can_keep_literal_source_duration_text(endpoint):
    text = (ROOT / "E1.txt").read_text().replace("настоящее время", endpoint)
    captured = request(text)
    raw = employment_proposal(captured).model_dump(by_alias=True)
    period = raw["jobs"][0]["periods"][0]
    period["endText"] = endpoint
    reply = GuiSemanticProposal.model_validate(raw)
    result = normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    normalized = result.job_periods[result.employment[0].id][0]
    assert normalized.present and normalized.end is None and normalized.end_text == ""
    assert any(endpoint in span.text for span in normalized.evidence)


def test_present_endpoint_duration_does_not_allow_unsupported_text_or_a_past_endpoint():
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    period = raw["jobs"][0]["periods"][0]
    period["endText"] = "по настоящее время (invented duration)"
    reply = GuiSemanticProposal.model_validate(raw)
    with pytest.raises(NormalizationFailure) as error:
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert error.value.code == "UNSUPPORTED_PERIOD_TEXT"
    period["endText"] = "2020"
    reply = GuiSemanticProposal.model_validate(raw)
    with pytest.raises(NormalizationFailure) as error:
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    assert error.value.code == "INVALID_PRESENT_PERIOD"


@pytest.mark.parametrize("change", [None, "gap", "page", "outside", "partial", "revision", "source_revision", "ambiguous", "invented", "unowned"])
def test_joined_fact_quote_splits_only_at_verified_owned_pdf_continuation(change):
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    document = captured.sources[0]
    fact = next(row for row in raw["facts"] if row["tempId"] == "north-task")
    span = fact["literalEvidence"][0]
    first = next(unit for unit in document.units if unit.id == span["unitId"])
    second = first.model_copy(deep=True)
    second.id += "-continuation"
    second.order += 1
    for unit in document.units:
        if unit.order >= second.order:
            unit.order += 1
    first.text, second.text = "Built event pipeline", "with exact source words. Extra context."
    for unit in (first, second):
        unit.location.kind, unit.location.index = "page", 0
    document.units.append(second)
    claim = "Built event pipeline with exact source words."
    fact["value"]["text"], span["text"] = claim, claim
    job = next(row for row in raw["jobs"] if row["tempId"] == fact["jobTempId"])
    job["unitIds"].append(second.id)
    if change == "gap": second.order += 1
    if change == "page": second.location.index += 1
    if change == "outside": job["unitIds"].remove(second.id)
    if change == "partial": first.text = "Other heading. " + first.text
    if change == "revision": span["unitRevision"] += 1
    if change == "source_revision": span["sourceRevision"] += 1
    if change == "ambiguous": second.text += " " + claim
    if change == "invented": span["text"] = claim.replace("exact", "invented")
    if change == "unowned": fact["jobTempId"] = None
    before = captured.model_dump(mode="json", by_alias=True)
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    kept = next(row for row in reply.facts if row.temp_id == fact["tempId"])
    assert captured.model_dump(mode="json", by_alias=True) == before
    assert len(kept.literal_evidence) == (2 if change is None else 1)
    if change is None:
        assert [span.text for span in kept.literal_evidence] == [first.text, "with exact source words."]
        assert kept.unit_ids == [first.id, second.id]
        assert kept.value.text == first.text + "\nwith exact source words."
        assert " ".join(kept.value.text.split()) == claim
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    else:
        with pytest.raises(NormalizationFailure) as error:
            normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
        assert error.value.code == "INVALID_SOURCE_EVIDENCE"


@pytest.mark.parametrize("change", [None, "no_copy", "different_claim", "importance", "invalid_copy", "invalid_owner", "duplicate_id"])
def test_misowned_duplicate_is_removed_only_when_its_exact_owned_claim_survives(change):
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    original = next(row for row in raw["facts"] if row["tempId"] == "north-task")
    wrong = deepcopy(original)
    wrong.update(tempId="wrong-copy", jobTempId="west")
    wrong["value"]["text"] = "Unsupported native paraphrase"
    raw["facts"].append(wrong)
    for unit in raw["units"]:
        if original["tempId"] in unit["factTempIds"]:
            unit["factTempIds"].append(wrong["tempId"])
    if change == "no_copy":
        raw["facts"].remove(original)
        for unit in raw["units"]:
            unit["factTempIds"] = [id for id in unit["factTempIds"] if id != original["tempId"]]
    if change == "different_claim": wrong["literalEvidence"][0]["text"] = "Делала REST API"
    if change == "importance": wrong["importance"] = "essential"
    if change == "invalid_copy": original["literalEvidence"][0]["unitRevision"] += 1
    if change == "invalid_owner": original["jobTempId"] = "west"
    if change == "duplicate_id": wrong["tempId"] = original["tempId"]
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    if change is None:
        assert len(reply.facts) == len(raw["facts"]) - 1
        assert not any(fact.temp_id == wrong["tempId"] for fact in reply.facts)
        assert not any(wrong["tempId"] in unit.fact_temp_ids for unit in reply.units)
        kept = next(fact for fact in reply.facts if fact.temp_id == original["tempId"])
        assert kept.literal_evidence[0].model_dump(by_alias=True) == original["literalEvidence"][0]
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    else:
        assert len(reply.facts) == len(raw["facts"])
        with pytest.raises(NormalizationFailure):
            normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))


@pytest.mark.parametrize("change", [None, "revision", "invented", "owned"])
def test_unsupported_global_technology_keeps_one_verified_literal_without_tool_or_duration(change):
    captured = source()
    raw = employment_proposal(captured).model_dump(by_alias=True)
    fact = next(row for row in raw["facts"] if row["tempId"] == "docker")
    fact["value"].update(display="Invented Tool", canonicalId="invented-tool")
    if change == "revision": fact["literalEvidence"][0]["unitRevision"] += 1
    if change == "invented": fact["literalEvidence"][0]["text"] = "Invented citation"
    if change == "owned":
        fact.update(jobTempId="north")
        fact["value"]["scope"] = "job"
    reply = NormalizationTransport(captured).restore(GuiSemanticProposal.model_validate(raw))
    kept = next(row for row in reply.facts if row.temp_id == fact["tempId"])
    if change is None:
        assert kept.kind == "text" and kept.value.text == "Docker"
        assert kept.job_temp_id is None and kept.subproject_temp_id is None
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    else:
        assert kept.kind == "technology"
        with pytest.raises(NormalizationFailure):
            normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))


@pytest.mark.parametrize("change", ["alias", "canonical", "foreign", "unknown", "empty", "duplicate", "collision"])
def test_job_unit_accounting_omits_only_its_own_redundant_source_label(change):
    captured = source()
    if change == "collision": captured.sources[0].id = captured.sources[0].units[1].id
    raw = employment_proposal(captured).model_dump(by_alias=True)
    transport = NormalizationTransport(captured)
    job = raw["jobs"][0]
    expected = list(job["unitIds"])
    label = transport.source_aliases[job["sourceId"]]
    if change == "canonical": label = job["sourceId"]
    if change == "foreign": label = "s999"
    if change == "unknown": label = "u999"
    if change == "empty": job["unitIds"] = []
    if change == "duplicate": label = job["unitIds"][0]
    if change != "collision": job["unitIds"].insert(0, label)
    reply = transport.restore(GuiSemanticProposal.model_validate(raw))
    if change in {"alias", "canonical", "collision"}:
        assert reply.jobs[0].unit_ids == expected
        normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
    else:
        with pytest.raises(NormalizationFailure) as error:
            normalize_employment(captured, reply, normalize_candidate(captured, reply, RULES))
        assert error.value.code == "INVALID_JOB_EVIDENCE"
