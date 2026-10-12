"""One no-repair GUI rewrite request with code-owned scope validation."""

from pydantic import ValidationError

from packages.resume_core.gui_rewriting import GuiRewriteProposal, validate_replacements
from .gui_content import generate_admitted
from .providers.content import ContentFailure, ContentInput, GenerationPolicy


class GuiRewritingContentService:
    def __init__(self, provider, model):
        self.provider = provider
        self.policy = GenerationPolicy(model=model, allow_repair=False)

    def run(self, prompt, selection, files, cancel):
        response = generate_admitted(self.provider, ContentInput(prompt, GuiRewriteProposal, self.policy), files, cancel)
        if cancel.is_set():
            raise ContentFailure("CANCELLED", logical_attempts=response.logical_attempts, usage=response.usage)
        try:
            proposal = validate_replacements(selection, GuiRewriteProposal.model_validate(response.value))
        except (ValidationError, ValueError, UnicodeError):
            raise ContentFailure("INVALID_RESULT", logical_attempts=response.logical_attempts, usage=response.usage) from None
        return proposal, response
