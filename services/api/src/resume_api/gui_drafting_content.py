"""One no-repair GUI draft request, followed by pure plan/document validation."""

import threading
from pydantic import ValidationError

from packages.resume_core.gui_drafting import GuiDraftRequest, GuiDraftProposal, drafting_input, validate_draft
from packages.resume_core.gui_draft_recovery import DraftWarnings
from packages.resume_core.models.recovery import Rules

from .gui_content import generate_admitted
from .gui_drafting_transport import DraftingTransport
from .lifecycle import OperationFiles
from .providers.content import ContentFailure, ContentInput, ContentProvider, GenerationPolicy, MAX_GENERATION_SECONDS


class GuiDraftingContentService:
    def __init__(self, provider: ContentProvider, model: str):
        self.provider = provider
        self.policy = GenerationPolicy(model=model, timeout_seconds=MAX_GENERATION_SECONDS, allow_repair=False)

    def run(self, request: GuiDraftRequest, rules: Rules, files: OperationFiles, cancel: threading.Event):
        captured = request.model_copy(deep=True)
        transport = DraftingTransport(captured)
        recovered = False
        try:
            prompt = drafting_input(captured, rules, transform=transport.encode, return_canonical=True)
        except ValueError as error:
            if str(error) not in {"INPUT_TOO_LARGE", "INVALID_CONTENT_INPUT"}:
                raise
            raise ContentFailure(str(error)) from None
        try:
            response = generate_admitted(self.provider, ContentInput(prompt, GuiDraftProposal,
                self.policy, transport), files, cancel)
            value, attempts, usage, count = response.value, response.logical_attempts, response.usage, response.internal_inference_count
        except ContentFailure as error:
            if error.code != "INVALID_RESULT" or cancel.is_set():
                raise
            value, attempts, usage, count = {}, error.logical_attempts, error.usage, None
            recovered = True
        if cancel.is_set():
            raise ContentFailure("CANCELLED", logical_attempts=attempts, usage=usage)
        try:
            proposal = GuiDraftProposal.model_validate(value)
        except (ValidationError, ValueError):
            proposal = transport.decode(value)
            recovered = True
        result = validate_draft(captured, proposal, rules)
        if recovered or transport.incoming.unresolved:
            warnings = DraftWarnings(captured, rules)
            warnings.add("IMPORT_CONTENT_RECOVERED")
            result.annotations.extend(warnings.marks.values())
        return result, {"logicalAttempts": attempts, "inputTokens": usage.input_tokens,
                        "outputTokens": usage.output_tokens, "inferenceCount": count}
