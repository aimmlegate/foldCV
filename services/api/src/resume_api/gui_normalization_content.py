"""One shared candidate/employment content request for the GUI pipeline."""

import threading
from pydantic import ValidationError

from packages.resume_core.gui_normalization import GuiNormalizeRequest, GuiSemanticProposal, NormalizationFailure, normalize_candidate, normalization_input
from packages.resume_core.models.recovery import Rules
from packages.resume_core.gui_employment import normalize_employment

from .gui_content import generate_admitted
from .gui_native_transport import NativeNormalizationTransport
from .lifecycle import OperationFiles
from .providers.content import ContentFailure, ContentInput, ContentProvider, GenerationPolicy, MAX_GENERATION_SECONDS


class GuiNormalizationContentService:
    def __init__(self, provider: ContentProvider, model: str):
        self.provider = provider
        self.policy = GenerationPolicy(model=model, timeout_seconds=MAX_GENERATION_SECONDS, allow_repair=False)

    def run(self, request: GuiNormalizeRequest, rules: Rules, files: OperationFiles, cancel: threading.Event):
        captured = request.model_copy(deep=True)
        transport = NativeNormalizationTransport(captured, rules)
        prompt = normalization_input(captured, rules)
        response = generate_admitted(self.provider, ContentInput(prompt, GuiSemanticProposal, self.policy, transport), files, cancel)
        if cancel.is_set():
            raise ContentFailure("CANCELLED", logical_attempts=response.logical_attempts, usage=response.usage)
        try:
            proposal = GuiSemanticProposal.model_validate(response.value)
            result = normalize_candidate(captured, proposal, rules)
            result = normalize_employment(captured, proposal, result)
            result._native_recovery_count = transport.unresolved
        except NormalizationFailure as error:
            raise ContentFailure(error.code, logical_attempts=response.logical_attempts, usage=response.usage) from None
        except (ValidationError, ValueError):
            raise ContentFailure("INVALID_RESULT", logical_attempts=response.logical_attempts, usage=response.usage) from None
        return result, {"logicalAttempts": response.logical_attempts, "inputTokens": response.usage.input_tokens,
                        "outputTokens": response.usage.output_tokens, "inferenceCount": response.internal_inference_count}
