"""The single bounded rewrite operation; production access stays closed."""

from __future__ import annotations

import threading

from packages.resume_core.rewriting import RewriteProposal, RewriteRequest, RewriteResult, rewrite_input, validate_rewrite

from .lifecycle import OperationFiles
from .providers.content import ContentInput, ContentProvider, GenerationPolicy


class RewritingContentService:
    def __init__(self, provider: ContentProvider, model: str):
        self.provider = provider
        self.policy = GenerationPolicy(model=model)

    def run(self, request: RewriteRequest, files: OperationFiles,
            cancel: threading.Event) -> tuple[RewriteResult, dict[str, int | None]]:
        prompt = rewrite_input(request)
        if cancel.is_set():
            raise InterruptedError("cancelled")
        result = self.provider.generate(ContentInput(prompt, RewriteProposal, self.policy), files, cancel)
        if cancel.is_set():
            raise InterruptedError("cancelled")
        proposal = RewriteProposal.model_validate(result.value)
        validated = validate_rewrite(request, proposal)
        return validated, {"logicalAttempts": result.logical_attempts,
                           "inputTokens": result.usage.input_tokens,
                           "outputTokens": result.usage.output_tokens,
                           "inferenceCount": result.internal_inference_count}
