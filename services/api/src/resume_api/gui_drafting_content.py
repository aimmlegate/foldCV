"""One no-repair GUI draft request, followed by pure plan/document validation."""

import threading
from pydantic import ValidationError

from packages.resume_core.gui_drafting import GuiDraftRequest, GuiDraftProposal, DraftFailure, drafting_input, validate_draft
from packages.resume_core.models.recovery import Rules

from .gui_content import generate_admitted
from .lifecycle import OperationFiles
from .providers.content import ContentFailure, ContentInput, ContentProvider, GenerationPolicy


class GuiDraftingContentService:
    def __init__(self, provider: ContentProvider, model: str):
        self.provider = provider
        self.policy = GenerationPolicy(model=model, timeout_seconds=60, allow_repair=False)

    def run(self, request: GuiDraftRequest, rules: Rules, files: OperationFiles, cancel: threading.Event):
        captured = request.model_copy(deep=True)
        response = generate_admitted(self.provider, ContentInput(drafting_input(captured, rules), GuiDraftProposal, self.policy), files, cancel)
        if cancel.is_set():
            raise ContentFailure("CANCELLED", logical_attempts=response.logical_attempts, usage=response.usage)
        try:
            proposal = GuiDraftProposal.model_validate(response.value)
            result = validate_draft(captured, proposal, rules)
        except DraftFailure as error:
            raise ContentFailure(error.code, logical_attempts=response.logical_attempts, usage=response.usage) from None
        except (ValidationError, ValueError):
            raise ContentFailure("INVALID_RESULT", logical_attempts=response.logical_attempts, usage=response.usage) from None
        return result, {"logicalAttempts": response.logical_attempts, "inputTokens": response.usage.input_tokens,
                        "outputTokens": response.usage.output_tokens, "inferenceCount": response.internal_inference_count}
