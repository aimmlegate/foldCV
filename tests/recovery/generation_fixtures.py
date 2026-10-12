"""Controlled replies connected to the actual selected synthetic source IDs."""

from datetime import datetime, timezone
import json

from packages.resume_core.gui_drafting import GuiDraftProposal, GuiDraftRequest, validate_draft
from packages.resume_core.gui_normalization import GuiNormalizeRequest, GuiSemanticProposal, normalize_candidate
from packages.resume_core.gui_rewriting import GuiRewriteProposal
from packages.resume_core.gui_employment import normalize_employment
from packages.resume_core.gui_derived import initial_derived
from packages.resume_core.models.recovery import WorkspaceV5, record_slot
from packages.resume_core.rules import captured_rules
from resume_api.providers.content import ContentResult, ContentFailure, ReportedUsage
from tests.recovery.draft_fixtures import draft_request, draft_reply, RULES
from tests.recovery.employment_fixtures import employment_proposal
from tests.recovery.test_recovery_contracts import fixture


def frozen_now():
    return datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


class CreationProvider:
    def __init__(self, example="E1", fail_kind=None, remove_focus=False):
        self.example, self.fail_kind = example, fail_kind
        self.remove_focus = remove_focus
        self.calls = []
        self.normalized = None

    def generate_queued(self, request, files, cancel, admitted):
        admitted()
        return self.generate(request, files, cancel)

    def generate(self, request, _files, _cancel):
        payload = json.loads(request.text)
        self.calls.append(payload)
        assert request.policy.allow_repair is False
        if request.result_type.__name__ == self.fail_kind:
            raise ContentFailure("MODEL_DENIED")
        rules = captured_rules(payload["rulesUsed"]["markdown"], payload["rulesUsed"]["revision"])
        if request.result_type is GuiSemanticProposal:
            captured = GuiNormalizeRequest.model_validate({key: payload["input"][key] for key in ("sources", "formattingAsOf", "revision")})
            self.formatting_as_of = captured.formatting_as_of
            reply = employment_proposal(captured, self.example)
            self.normalized = normalize_employment(captured, reply, normalize_candidate(captured, reply, rules))
        elif request.result_type is GuiRewriteProposal:
            if payload["input"]["instruction"] == "TEST_ERROR":
                raise ContentFailure("MODEL_DENIED")
            reply = GuiRewriteProposal(replacements=[{"fieldId": span["fieldId"],
                "text": "Яснее: " + span["capturedText"]} for span in payload["input"]["selection"]])
        else:
            assert request.result_type is GuiDraftProposal
            captured = GuiDraftRequest(projectId=payload["input"]["projectId"], projectRevision=1, documentRevision=1,
                normalized=self.normalized, formattingAsOf=self.formatting_as_of)
            reply = draft_reply(captured, rules_revision=rules.revision, example=self.example)
            if self.remove_focus:
                reply.editorial_plan.focus.append(reply.editorial_plan.focus[0].model_copy(update={"catalog_id": "unknown"}))
        return ContentResult(reply, ReportedUsage(input_tokens=11, output_tokens=7), "fixture", request.policy.model, 0.01, 1)


def frozen_now_partial():
    from packages.resume_core.dates import partial_date
    return partial_date("2026-10-11")


def render_workspace(example="E1"):
    request = draft_request(example)
    result = validate_draft(request, draft_reply(request, example=example), RULES)
    raw = fixture("workspace_v5")
    raw["project"].update(document=result.document.model_dump(by_alias=True),
        sources=[item.model_dump(by_alias=True) for item in request.normalized.sources],
        facts=[item.model_dump(by_alias=True) for item in request.normalized.facts],
        employment=[item.model_dump(by_alias=True) for item in request.normalized.employment], operations=[], renders=[])
    raw.update(editorialPlan=result.editorial_plan.model_dump(by_alias=True), annotations=[], generations=[],
        undoSlots={record_slot(record): None for record in result.document.records()}, editSessions={}, sourceObservedAt=None)
    workspace = WorkspaceV5.model_validate(raw)
    workspace.derived_state = initial_derived(result.document, workspace.project.facts, workspace.project.employment,
        None, 2, result.editorial_plan.source_language)
    return workspace
