"""Native partial acceptance preserves proved rows and immutable source data."""

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_annotations import initial_annotations
from packages.resume_core.gui_drafting import GuiDraftRequest, draft_skeleton, drafting_input
from packages.resume_core.gui_employment import normalize_employment
from packages.resume_core.gui_normalization import GuiSemanticProposal, normalize_candidate, public_context_facts
from packages.resume_core.models.recovery import Dependencies
from resume_api.gui_native_transport import NativeNormalizationTransport
from resume_api.providers.codex_cli import Events, InvalidFinal
from resume_api.providers.structured_schema import StructuredSchema
from tests.recovery.candidate_fixtures import request, span, value
from tests.recovery.employment_fixtures import employment_proposal
from tests.recovery.test_normalization_transport import RULES, source


def recover(captured, raw):
    before = captured.model_dump(mode="json", by_alias=True)
    transport = NativeNormalizationTransport(captured, RULES)
    proposal = transport.restore(transport.decode(raw))
    result = normalize_employment(captured, proposal, normalize_candidate(captured, proposal, RULES))
    result._native_recovery_count = transport.unresolved
    assert captured.model_dump(mode="json", by_alias=True) == before
    assert [(row.id, row.revision, row.byte_sha256) for row in result.sources] == [
        (row.id, row.revision, row.byte_sha256) for row in captured.sources]
    assert [(unit.id, unit.revision, unit.text, unit.order) for row in result.sources for unit in row.units] == [
        (unit.id, unit.revision, unit.text, unit.order) for row in captured.sources for unit in row.units]
    return proposal, result, transport.unresolved


def test_supported_native_rows_keep_canonical_facts_without_partial_warning():
    captured = source()
    full = employment_proposal(captured)
    expected = normalize_employment(captured, full, normalize_candidate(captured, full, RULES))
    _, result, unresolved = recover(captured, full.model_dump(mode="json", by_alias=True))
    assert result.facts == expected.facts and result.employment == expected.employment
    assert result.candidate == expected.candidate and unresolved == 0


@pytest.mark.parametrize("change", ["citation", "ownership", "malformed", "unknown_kind"])
def test_one_bad_native_fact_does_not_block_other_jobs_or_verified_facts(change):
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    row = next(row for row in raw["facts"] if row["tempId"] == "north-task")
    original_unit = row["literalEvidence"][0]["unitId"]
    if change == "citation": row["literalEvidence"][0]["unitId"] = "foreign"
    if change == "ownership": row["jobTempId"] = "west"
    if change == "malformed": row["literalEvidence"] = [{"text": {"unexpected": "shape"}}]
    if change == "unknown_kind": row["kind"] = {"unexpected": "shape"}
    proposal, result, unresolved = recover(captured, raw)
    assert len(result.employment) == 3 and unresolved > 0
    assert not any(row.temp_id == "north-task" for row in proposal.facts)
    assert any(row.temp_id == "postgres" for row in proposal.facts)
    unit = next(unit for row in result.sources for unit in row.units if unit.id == original_unit)
    assert unit.disposition == "unresolved"


def test_sparse_native_fields_and_bad_detail_values_keep_independently_supported_values():
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    raw["candidate"]["name"]["text"] = "Invented Candidate"
    del raw["candidate"]["location"]
    raw["education"][0]["specialty"]["text"] = "Invented qualification"
    raw["languages"].append({"name": ["unexpected shape"]})
    _, result, unresolved = recover(captured, raw)
    assert result.candidate.name.text == result.candidate.location.text == ""
    assert result.candidate.title.text == "backend-разработчик"
    assert result.education[0].institution.text == "Учебный технический университет"
    assert result.education[0].specialty.text == ""
    assert len(result.languages) == 2 and unresolved > 0


def test_native_missing_fact_bookkeeping_uses_only_explicit_evidence_references():
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    row = next(row for row in raw["facts"] if row["tempId"] == "north-task")
    for key in ("tempId", "sourceId", "unitIds"):
        del row[key]
    proposal, _, _ = recover(captured, raw)
    kept = next(fact for fact in proposal.facts if fact.kind == "text" and fact.value.text == row["value"]["text"])
    assert kept.source_id == row["literalEvidence"][0]["sourceId"]
    assert kept.unit_ids == [row["literalEvidence"][0]["unitId"]]


def test_native_bad_extra_citation_does_not_erase_an_independently_proved_field_or_fact():
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    raw["candidate"]["name"]["evidence"].append({"sourceId": "foreign", "sourceRevision": 1,
        "unitId": "foreign", "unitRevision": 1, "text": "Foreign citation"})
    row = next(row for row in raw["facts"] if row["tempId"] == "north-task")
    row["literalEvidence"].append(deepcopy(raw["candidate"]["name"]["evidence"][-1]))
    proposal, result, unresolved = recover(captured, raw)
    assert result.candidate.name.text == "Ирина Примерова" and unresolved > 0
    kept = next(fact for fact in proposal.facts if fact.temp_id == "north-task")
    assert len(kept.literal_evidence) == 1 and kept.value.text == row["value"]["text"]


def test_invalid_native_period_keeps_job_and_only_verified_literal_endpoints():
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    period = raw["jobs"][0]["periods"][0]
    period.update(startText="2021", endText="Invented endpoint", end={"precision": "year", "year": 2035})
    _, result, unresolved = recover(captured, raw)
    assert len(result.employment) == 3 and unresolved > 0
    period = result.job_periods[result.employment[0].id][0]
    assert period.start is None and period.end is None and not period.present
    assert period.start_text == "2021" and period.end_text == ""


def test_native_unknown_job_does_not_reassign_its_claims_to_other_jobs():
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    raw["jobs"][0]["employer"] = "Invented Employer"
    proposal, result, unresolved = recover(captured, raw)
    assert len(result.employment) == 2 and unresolved > 0
    assert not any(row.job_temp_id == "north" for row in proposal.facts)
    assert any(row.job_temp_id == "west" for row in proposal.facts)


def test_native_unit_accounting_is_derived_once_from_surviving_facts():
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    raw["units"] = [{"sourceId": "foreign", "unitId": "foreign", "disposition": "duplicate", "factTempIds": ["unknown"]}]
    proposal, _, _ = recover(captured, raw)
    assert len(proposal.units) == sum(len(row.units) for row in captured.sources)
    assert len({(row.source_id, row.unit_id) for row in proposal.units}) == len(proposal.units)
    assert all(row.duplicate_of is None for row in proposal.units)
    assert {id for row in proposal.units for id in row.fact_temp_ids} == {row.temp_id for row in proposal.facts}


@pytest.mark.parametrize("private_text", ["Unsupported joined private value", {"unexpected": "shape"}, None, "x" * 4001])
def test_malformed_candidate_detail_preserves_supported_fragments_and_neighbor_fact(private_text):
    text = (Path(__file__).parents[1] / "fixtures/recovery/E1.txt").read_text()
    text += "Email: fictional@example.invalid\nPhone: +12345678901\n"
    captured = request(text)
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    email = value(captured.sources[0], "fictional@example.invalid")
    phone = value(captured.sources[0], "+12345678901")
    raw["privateDetails"] = [{"kind": {"unexpected": "shape"}, "value": {
        "text": private_text, "evidence": [*email["evidence"], *phone["evidence"]]}}]
    raw["facts"].append({"tempId": "public-contact", "kind": "text", "value": {"text": email["text"]},
        "sourceId": captured.sources[0].id, "unitIds": [email["evidence"][0]["unitId"]],
        "jobTempId": None, "subprojectTempId": None, "importance": "normal", "literalEvidence": email["evidence"]})
    proposal, result, unresolved = recover(captured, raw)
    assert unresolved > 0 and len(result.private_details) == 2
    assert any(row.temp_id == "public-contact" for row in proposal.facts)
    assert any(getattr(row.value, "text", "") == email["text"] for row in public_context_facts(result.facts))
    draft = GuiDraftRequest(projectId="project-native", projectRevision=1, documentRevision=1,
        normalized=result, formattingAsOf=captured.formatting_as_of)
    public = drafting_input(draft, RULES)
    assert email["text"] in public and phone["text"] in public


def test_native_decoder_recovers_one_bad_row_before_whole_model_validation():
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    raw["facts"].append({"kind": {"unexpected": "shape"}})
    events = Events()
    events.complete, events.text = True, json.dumps(raw)
    schema = StructuredSchema(GuiSemanticProposal.model_json_schema())
    with pytest.raises(InvalidFinal):
        events.result(GuiSemanticProposal, schema)
    transport = NativeNormalizationTransport(captured, RULES)
    proposal = transport.restore(events.result(GuiSemanticProposal, schema, transport.decode))
    result = normalize_employment(captured, proposal, normalize_candidate(captured, proposal, RULES))
    assert len(result.employment) == 3 and transport.unresolved > 0


@pytest.mark.parametrize("raw", [[], {"unrelated": "envelope"}, {"schemaVersion": 2, "jobs": []},
    {"schemaVersion": True, "facts": []}, {"facts": [{}] * 501}])
def test_native_envelope_versions_and_size_limits_remain_fatal(raw):
    with pytest.raises(ValueError):
        NativeNormalizationTransport(source(), RULES).decode(raw)


def test_native_partial_warning_is_located_without_changing_wire_or_authored_text():
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    raw["candidate"]["name"]["text"] = "Invented Candidate"
    _, normalized, count = recover(captured, raw)
    document = draft_skeleton(normalized)
    before = document.model_dump()
    dependencies = Dependencies(projectRevision=1, documentRevision=1, rulesSha256=RULES.sha256,
        sourceFingerprint=normalized.source_fingerprint, dependencyFingerprint="a" * 64)
    marks = initial_annotations("project-native", document, normalized, [], dependencies)
    warning = next(mark for mark in marks if mark.code == "source_details_unresolved")
    assert count > 0 and warning.type == "warning" and warning.anchor.kind == "document"
    assert warning.dependencies == dependencies and not warning.fact_ids and not warning.evidence
    assert document.model_dump() == before
    assert "_native_recovery_count" not in normalized.model_dump_json()


@pytest.mark.parametrize("stage", ["decode", "restore"])
@pytest.mark.parametrize("failure", ["CANCELLED", "TIMEOUT"])
def test_native_guard_interrupts_allowed_large_proposal_before_unbounded_probes(stage, failure):
    from resume_api.lifecycle import SpikeError
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    row = next(row for row in raw["facts"] if row["tempId"] == "north-task")
    raw["facts"] = [{**deepcopy(row), "tempId": f"claim-{index}"} for index in range(500)]
    transport = NativeNormalizationTransport(captured, RULES)
    decoded = transport.decode(raw) if stage == "restore" else None
    calls = 0

    def guard():
        nonlocal calls
        calls += 1
        if calls == 50:
            raise SpikeError(failure)

    transport.bind_guard(guard)
    with pytest.raises(SpikeError, match=failure):
        transport.restore(decoded) if stage == "restore" else transport.decode(raw)
    assert calls == 50
    assert len(captured.sources[0].units) > 0


@pytest.mark.asyncio
async def test_partial_warning_survives_cached_draft_retry_and_durable_service_reopen(tmp_path):
    from tests.recovery.generation_fixtures import CreationProvider
    from tests.recovery.test_project_store import service
    from tests.recovery.test_gui_projects import finish
    from resume_api.providers.content import ContentResult

    class PartialProvider(CreationProvider):
        def generate(self, request, files, cancel):
            response = super().generate(request, files, cancel)
            if request.result_type is GuiSemanticProposal:
                raw = response.value.model_dump(mode="json", by_alias=True)
                raw["candidate"]["name"]["text"] = "Unsupported name"
                recovered = request.transport.restore(request.transport.decode(raw))
                captured = request.transport.request
                rules = request.transport.recovery.rules
                self.normalized = normalize_employment(captured, recovered, normalize_candidate(captured, recovered, rules))
                return ContentResult(recovered, response.usage, response.cli_version,
                                     response.model, response.elapsed_seconds, response.logical_attempts)
            return response

    provider = PartialProvider(fail_kind="GuiDraftProposal")
    store = service(tmp_path, provider)
    selected = await store.select((Path(__file__).parents[1] / "fixtures/recovery/E1.txt").read_bytes(), "pasted.txt", True)
    first = store.start(selected.project_id)
    await finish(store, selected.project_id, first)
    assert store.read(selected.project_id).generations[-1].status == "failed"
    assert store.cache[(selected.project_id, first)]["normalized"]._native_recovery_count > 0
    provider.fail_kind = None
    await finish(store, selected.project_id, store.start(selected.project_id, previous=first))
    current = store.read(selected.project_id)
    assert current.generations[-1].status == "completed", [(stage.kind, stage.error_code) for stage in current.generations[-1].stages]
    assert len([call for call in provider.calls if call["task"] == "normalize_semantics"]) == 1
    warning = next(mark for mark in current.annotations if mark.code == "source_details_unresolved")
    reopened = service(tmp_path, CreationProvider()).read(selected.project_id)
    assert next(mark for mark in reopened.annotations if mark.code == "source_details_unresolved") == warning
    assert reopened.project.sources == current.project.sources


@pytest.mark.parametrize('job_index', [0, 1])
def test_malformed_period_text_keeps_independently_supported_date_endpoints(job_index):
    captured = source()
    raw = employment_proposal(captured).model_dump(mode="json", by_alias=True)
    expected = deepcopy(raw['jobs'][job_index]['periods'][0])
    raw['jobs'][job_index]['periods'][0]['endText'] = {'unexpected': 'shape'}
    _, result, count = recover(captured, raw)
    period = result.job_periods[result.employment[job_index].id][0]
    assert period.start.model_dump(by_alias=True) == expected['start']
    assert (period.end.model_dump(by_alias=True) if period.end else None) == expected['end']
    assert count > 0 and len(result.employment) == 3


def test_sparse_empty_native_reply_keeps_full_source_accounting_and_warning():
    captured = source()
    proposal, result, count = recover(captured, {'facts': []})
    assert count > 0 and not result.employment
    assert len(proposal.units) == sum(len(source.units) for source in captured.sources)
    assert all(unit.disposition == 'unresolved' for unit in proposal.units)


def test_unrepresented_source_remains_warned_without_native_row_drops():
    text = (Path(__file__).parents[1] / 'fixtures/recovery/E1.txt').read_text()
    captured = request(text + '\nAdditional unsupported source detail.\n')
    _, normalized, count = recover(captured, employment_proposal(captured).model_dump(mode='json', by_alias=True))
    assert count == 0
    document = draft_skeleton(normalized)
    deps = Dependencies(projectRevision=1, documentRevision=1, rulesSha256=RULES.sha256,
        sourceFingerprint=normalized.source_fingerprint, dependencyFingerprint='a' * 64)
    before = document.model_dump()
    marks = initial_annotations('unrepresented-source', document, normalized, [], deps)
    assert any(mark.code == 'source_details_unresolved' and mark.type == 'warning' for mark in marks)
    assert document.model_dump() == before
    unit = normalized.sources[0].units[-1]
    assert unit.disposition == 'unresolved' and unit.text == 'Additional unsupported source detail.\n'


def test_unsupported_owned_technology_display_keeps_exact_claim_without_inventing_tool():
    captured = source()
    raw = employment_proposal(captured).model_dump(mode='json', by_alias=True)
    row = next(row for row in raw['facts'] if row['tempId'] == 'postgres')
    literal = '\n'.join(span['text'] for span in row['literalEvidence'])
    owner = row['jobTempId']
    row['value']['display'] = 'Unverified technology'
    proposal, result, count = recover(captured, raw)
    kept = next(fact for fact in proposal.facts if fact.temp_id == 'postgres')
    assert kept.kind == 'text' and kept.value.text == literal and kept.job_temp_id == owner
    assert count > 0 and len(result.employment) == 3
    assert 'Unverified technology' not in result.model_dump_json()


def test_literal_fallback_cannot_move_foreign_claim_inside_another_job():
    captured = source()
    raw = employment_proposal(captured).model_dump(mode='json', by_alias=True)
    row = next(row for row in raw['facts'] if row['tempId'] == 'postgres')
    row['value']['display'] = 'Unverified technology'
    row['jobTempId'] = 'west'
    proposal, result, count = recover(captured, raw)
    assert not any(fact.temp_id == 'postgres' for fact in proposal.facts)
    assert count > 0 and len(result.employment) == 3
