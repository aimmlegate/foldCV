"""The single bounded draft operation; production access stays closed."""

from __future__ import annotations

import threading

from packages.resume_core.drafting import DraftProposal, DraftRequest, DraftResult, draft_input, validate_draft

from .lifecycle import OperationFiles
from .providers.content import ContentInput, ContentProvider, GenerationPolicy


class DraftingContentService:
    def __init__(self, provider: ContentProvider, model: str):
        self.provider = provider
        self.policy = GenerationPolicy(model=model)

    def run(self, request: DraftRequest, files: OperationFiles,
            cancel: threading.Event) -> tuple[DraftResult, dict[str, int | None]]:
        prompt = draft_input(request)
        if cancel.is_set():
            raise InterruptedError("cancelled")
        result = self.provider.generate(ContentInput(prompt, DraftProposal, self.policy), files, cancel)
        if cancel.is_set():
            raise InterruptedError("cancelled")
        proposal = DraftProposal.model_validate(result.value)
        validated = validate_draft(request, proposal)
        return validated, {"logicalAttempts": result.logical_attempts,
                           "inputTokens": result.usage.input_tokens,
                           "outputTokens": result.usage.output_tokens,
                           "inferenceCount": result.internal_inference_count}
