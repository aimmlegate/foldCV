"""One admitted reconciliation attempt; malformed replies never get repaired."""

from pydantic import ValidationError
from packages.resume_core.gui_reconciliation import GuiReconcileProposal, validate_proposal
from .gui_content import generate_admitted
from .providers.content import ContentFailure, ContentInput, GenerationPolicy


class GuiReconciliationContentService:
    def __init__(self, provider, model):
        self.provider = provider
        self.policy = GenerationPolicy(model=model, allow_repair=False)

    def run(self, prompt, captured, fields, files, cancel):
        response = generate_admitted(self.provider, ContentInput(prompt, GuiReconcileProposal, self.policy), files, cancel)
        if cancel.is_set(): raise ContentFailure('CANCELLED', logical_attempts=response.logical_attempts, usage=response.usage)
        try:
            result = validate_proposal(captured, fields, GuiReconcileProposal.model_validate(response.value))
        except (ValidationError, ValueError, UnicodeError):
            raise ContentFailure('INVALID_RESULT', logical_attempts=response.logical_attempts, usage=response.usage) from None
        return result, response
