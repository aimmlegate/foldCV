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
        recovered = False
        try:
            response = generate_admitted(self.provider, ContentInput(prompt, GuiSemanticProposal, self.policy, transport), files, cancel)
            value, attempts, usage, count = response.value, response.logical_attempts, response.usage, response.internal_inference_count
        except ContentFailure as error:
            if error.code != "INVALID_RESULT" or cancel.is_set():
                raise
            value, attempts, usage, count = {"candidate": {}}, error.logical_attempts, error.usage, None
            recovered = True
        if cancel.is_set():
            raise ContentFailure("CANCELLED", logical_attempts=attempts, usage=usage)
        try:
            proposal = GuiSemanticProposal.model_validate(value)
            result = normalize_candidate(captured, proposal, rules)
            result = normalize_employment(captured, proposal, result)
        except (NormalizationFailure, ValidationError, ValueError):
            raw = value.model_dump(mode="json", by_alias=True) if isinstance(value, GuiSemanticProposal) else value
            if not isinstance(raw, dict) or not {"candidate", "jobs", "facts"}.intersection(raw):
                raw = {"candidate": {}}
            raw = {**raw, "schemaVersion": 1}
            proposal = transport.recovery.recover(transport.incoming.parse(raw))
            result = normalize_employment(captured, proposal, normalize_candidate(captured, proposal, rules))
            recovered = True
        result._native_recovery_count = transport.unresolved + int(recovered)
        return result, {"logicalAttempts": attempts, "inputTokens": usage.input_tokens,
                        "outputTokens": usage.output_tokens, "inferenceCount": count}
