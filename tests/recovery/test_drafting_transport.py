"""Native draft prompts expose writable prose without changing canonical data."""

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_drafting import GuiDraftProposal, DraftFailure, drafting_input, validate_draft
from resume_api.gui_drafting_transport import DraftingTransport
from tests.recovery.draft_fixtures import RULES, draft_request, draft_reply


def test_native_draft_prompt_preserves_all_jobs_claims_rules_and_source_excerpts():
    request = draft_request()
    canonical = drafting_input(request, RULES)
    original = json.loads(canonical)
    transport = DraftingTransport(request)
    compact = json.loads(transport.encode(canonical))
    assert compact["rulesUsed"] == original["rulesUsed"]
    assert compact["input"]["formattingAsOf"] == original["input"]["formattingAsOf"]
    assert compact["input"]["sourceExcerpts"] == original["input"]["sourceExcerpts"]
    assert [transport.jobs[row["id"]] for row in compact["input"]["activeJobs"]] == [job.id for job in request.normalized.employment]
    assert [transport.facts[row["id"]] for row in compact["input"]["facts"]] == [row["id"] for row in original["input"]["facts"]]
    assert "skeleton" not in compact["input"]
    writable = compact["input"]["writableFields"]
    assert len(writable) == 3 + 4 * len(request.normalized.employment)
    assert not any(transport.fields[row["fieldId"]].startswith("candidate/") for row in writable)
    facts = {row["id"]: row for row in compact["input"]["facts"]}
    for option in compact["input"]["focusOptions"]:
        assert option["factIds"]
        assert all(facts[id]["kind"] == "technology" and facts[id]["value"]["canonicalId"] == option["catalogId"]
                   for id in option["factIds"])
    assert len(transport.encode(canonical).encode()) < len(canonical.encode())
    assert drafting_input(request, RULES) == canonical


@pytest.mark.parametrize("example", ["E1", "E2"])
def test_short_draft_references_round_trip_to_the_same_validated_document(example):
    request = draft_request(example)
    reply = draft_reply(request, example=example)
    raw = reply.model_dump(mode="json", by_alias=True)
    before = deepcopy(raw)
    transport = DraftingTransport(request)

    def shorten(value):
        if isinstance(value, list):
            return [shorten(part) for part in value]
        if not isinstance(value, dict):
            return value
        return {key: transport.aliases.get(part, part) if key in {"jobId", "fieldId"} else
                [transport.aliases.get(ref, ref) for ref in part] if key == "factIds" else shorten(part)
                for key, part in value.items()}

    restored = transport.restore(GuiDraftProposal.model_validate(shorten(raw)))
    assert restored == reply
    assert restored.model_dump(mode="json", by_alias=True) == before
    assert validate_draft(request, restored, RULES) == validate_draft(request, reply, RULES)


@pytest.mark.parametrize("kind,code", [("field", "INVALID_DRAFT_FIELD_REFERENCE"),
    ("structured", "DRAFT_STRUCTURED_FIELD"), ("fact", "INVALID_DRAFT_FIELD_REFERENCE"),
    ("job", "INVALID_EDITORIAL_PLAN_CONTEXT")])
def test_draft_transport_does_not_drop_or_heal_invalid_references(kind, code):
    request = draft_request()
    raw = draft_reply(request).model_dump(by_alias=True)
    if kind == "field": raw["fields"][0]["fieldId"] = "unknown-field"
    if kind == "structured": raw["fields"][0]["fieldId"] = "candidate/name"
    if kind == "fact": raw["fields"][0]["factIds"] = ["unknown-fact"]
    if kind == "job": raw["editorialPlan"]["jobs"][0]["jobId"] = "unknown-job"
    reply = DraftingTransport(request).restore(GuiDraftProposal.model_validate(raw))
    with pytest.raises(DraftFailure) as error:
        validate_draft(request, reply, RULES)
    if kind == "structured":
        assert error.value.code in {"DRAFT_STRUCTURED_FIELD", "INCOMPLETE_DRAFT_FIELDS"}
        assert reply.fields[0].field_id == "candidate/name"
    else:
        assert error.value.code == code
