"""Content defects leave an editable import with durable, located warnings."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))

from packages.resume_core.gui_archive_validation import validate_workspace
from packages.resume_core.gui_drafting import GuiDraftProposal, validate_draft
from packages.resume_core.gui_employment import normalize_employment
from packages.resume_core.gui_normalization import GuiSemanticProposal, normalize_candidate
from packages.resume_core.models.recovery import WorkspaceV5
from resume_api.gui_drafting_content import GuiDraftingContentService
from resume_api.gui_drafting_transport import DraftingTransport
from resume_api.gui_normalization_content import GuiNormalizationContentService
from resume_api.lifecycle import OperationFiles
from resume_api.providers.codex_cli import Events
from resume_api.providers.content import ContentFailure, ContentResult, ReportedUsage
from resume_api.providers.structured_schema import StructuredSchema
from tests.recovery.draft_fixtures import RULES, draft_reply, draft_request
from tests.recovery.generation_fixtures import CreationProvider
from tests.recovery.candidate_fixtures import ROOT, request as normalization_request
from tests.recovery.test_gui_projects import finish
from tests.recovery.test_project_store import service


@pytest.mark.parametrize("scope", ["global", "other-job"])
def test_wrong_job_citations_and_unknown_references_preserve_text_and_neighboring_fields(scope):
    request = draft_request()
    reply = draft_reply(request)
    before = deepcopy(request.model_dump())
    first, second = request.normalized.employment[:2]
    refs = [fact.id for fact in request.normalized.facts if fact.kind == "technology"
            and fact.job_id == (None if scope == "global" else second.id)]
    target = next(field for field in reply.fields if field.field_id == f"job:{first.id}/stack")
    target.text, target.fact_ids = "Keep this stack exactly", [*refs, "unknown"]
    result = validate_draft(request, reply, RULES)
    stack = next(job for job in result.document.jobs if job.id == first.id).stack
    assert stack.text == target.text and stack.fact_ids == refs
    assert {"DRAFT_FACT_OUTSIDE_JOB", "INVALID_DRAFT_FIELD_REFERENCE"} <= {mark.code for mark in result.annotations}
    assert next(job for job in result.document.jobs if job.id == second.id).tasks.text == "Поддержка CRM и исправление ошибок."
    assert request.model_dump() == before


def test_duplicate_fields_combine_distinct_text_instead_of_overwriting_it():
    request = draft_request()
    reply = draft_reply(request)
    reply.fields.extend([reply.fields[0].model_copy(update={"text": "Another supported paragraph"}),
                         reply.fields[0].model_copy(deep=True)])
    result = validate_draft(request, reply, RULES)
    assert result.document.profile.text.text.count(reply.fields[0].text) == 1
    assert "Another supported paragraph" in result.document.profile.text.text
    assert "DUPLICATE_DRAFT_FIELD" in {mark.code for mark in result.annotations}


def test_malformed_native_neighbor_and_duplicate_plan_job_keep_all_valid_fields():
    request = draft_request()
    transport = DraftingTransport(request)
    raw = draft_reply(request).model_dump(mode="json", by_alias=True)
    raw["fields"].insert(1, {"fieldId": "profile/text", "text": {"bad": "shape"}, "factIds": []})
    raw["editorialPlan"]["jobs"].append(deepcopy(raw["editorialPlan"]["jobs"][0]))
    raw["editorialPlan"]["sourceLanguage"] = "unknown"
    events = Events()
    events.complete, events.text = True, json.dumps(raw)
    proposal = events.result(GuiDraftProposal, StructuredSchema(GuiDraftProposal.model_json_schema()), transport.decode)
    result = validate_draft(request, transport.restore(proposal), RULES)
    assert result.document.profile.text.text == raw["fields"][0]["text"]
    assert {job.job_id for job in result.editorial_plan.jobs} == {job.id for job in request.normalized.employment}
    assert transport.incoming.unresolved > 0


class InvalidResponse:
    def __init__(self, code="INVALID_RESULT"):
        self.code, self.calls = code, 0

    def generate(self, _request, _files, _cancel):
        self.calls += 1
        raise ContentFailure(self.code, logical_attempts=1, usage=ReportedUsage(input_tokens=11, output_tokens=7))


def test_invalid_draft_response_retains_literal_prose_and_accounts_for_single_call(tmp_path):
    captured = draft_request()
    provider = InvalidResponse()
    result, usage = GuiDraftingContentService(provider, "fixture").run(captured, RULES, OperationFiles(tmp_path), threading.Event())
    assert provider.calls == usage["logicalAttempts"] == 1
    assert usage["inputTokens"] == 11 and usage["outputTokens"] == 7
    assert result.document.profile.text.text and all(job.stack.text for job in result.document.jobs)
    assert len(result.document.jobs) == len(captured.normalized.employment)
    assert "IMPORT_CONTENT_RECOVERED" in {mark.code for mark in result.annotations}


def test_invalid_normalization_response_keeps_original_text_editable(tmp_path):
    request = normalization_request("Unusual resume layout\nKeep every source line\n")
    provider = InvalidResponse()
    normalized, usage = GuiNormalizationContentService(provider, "fixture").run(request, RULES, OperationFiles(tmp_path), threading.Event())
    assert usage["logicalAttempts"] == provider.calls == 1 and normalized._native_recovery_count > 0
    from packages.resume_core.gui_drafting import GuiDraftRequest
    draft = GuiDraftRequest(projectId="fallback", projectRevision=1, documentRevision=1,
                            normalized=normalized, formattingAsOf=request.formatting_as_of)
    result, _ = GuiDraftingContentService(InvalidResponse(), "fixture").run(draft, RULES, OperationFiles(tmp_path), threading.Event())
    assert result.document.profile.text.text == "\n".join(unit.text for unit in request.sources[0].units)
    assert [unit.text for unit in normalized.sources[0].units] == [unit.text for unit in request.sources[0].units]


@pytest.mark.parametrize("stage", ["normalization", "draft"])
@pytest.mark.parametrize("code", ["AUTH_REQUIRED", "CLI_FAILED", "TIMEOUT", "BUDGET_EXCEEDED", "CANCELLED"])
def test_technical_failures_are_not_misreported_as_successful_import(stage, code, tmp_path):
    provider = InvalidResponse(code)
    service_type, request = (GuiDraftingContentService, draft_request()) if stage == "draft" else (
        GuiNormalizationContentService, normalization_request("Readable source\n"))
    with pytest.raises(ContentFailure, match=code):
        service_type(provider, "fixture").run(request, RULES, OperationFiles(tmp_path), threading.Event())
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_warning_import_survives_durable_reopen_and_portable_reference_validation(tmp_path):
    class WrongScope(CreationProvider):
        def generate(self, request, files, cancel):
            response = super().generate(request, files, cancel)
            if request.result_type is GuiDraftProposal:
                reply = response.value.model_copy(deep=True)
                target = next(field for field in reply.fields if field.field_id.startswith("job:") and field.field_id.endswith("/stack"))
                target.text = "Keep the imported stack"
                target.fact_ids = [fact.id for fact in self.normalized.facts if fact.kind == "technology" and fact.job_id is None]
                return ContentResult(reply, response.usage, response.cli_version, response.model, response.elapsed_seconds, 1)
            return response
    provider = WrongScope()
    store = service(tmp_path, provider)
    selected = await store.select((ROOT / "E1.txt").read_bytes(), "pasted.txt", True)
    completed = await finish(store, selected.project_id, store.start(selected.project_id))
    assert completed.generations[-1].status == "completed" and len(provider.calls) == 2
    assert "DRAFT_FACT_OUTSIDE_JOB" in {mark.code for mark in completed.annotations}
    reopened = service(tmp_path, InvalidResponse()).read(selected.project_id)
    assert reopened.project.document.jobs[0].stack.text == "Keep the imported stack"
    assert reopened.annotations == completed.annotations
    validate_workspace(WorkspaceV5.model_validate(reopened.model_dump(mode="json", by_alias=True)))
