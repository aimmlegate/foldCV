"""The only semantic normalization boundary that receives a content provider."""

from __future__ import annotations

import threading

from packages.resume_core.normalization import (FactRequest, FactSheet, SemanticProposal,
                                                literal_sheet, merge_semantics, semantic_input)

from .lifecycle import OperationFiles
from .providers.content import ContentInput, ContentProvider, GenerationPolicy


class NormalizationContentService:
    def __init__(self, provider: ContentProvider, model: str):
        self.provider = provider
        self.policy = GenerationPolicy(model=model)

    def run(self, request: FactRequest, files: OperationFiles, cancel: threading.Event) -> tuple[FactSheet, dict[str, int | None]]:
        sheet = literal_sheet(request)
        prompt = semantic_input(sheet, request)
        if cancel.is_set():
            raise InterruptedError("cancelled")
        result = self.provider.generate(ContentInput(prompt, SemanticProposal, self.policy), files, cancel)
        proposal = SemanticProposal.model_validate(result.value)
        merged = merge_semantics(sheet, request, proposal)
        return merged, {"logicalAttempts": result.logical_attempts,
                        "inputTokens": result.usage.input_tokens,
                        "outputTokens": result.usage.output_tokens,
                        "inferenceCount": result.internal_inference_count}
