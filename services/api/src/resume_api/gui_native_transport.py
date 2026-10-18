"""Native-only tolerant decoding around the strict normalization transport."""

import json
from copy import deepcopy

from .gui_native_input import NativeInput
from .gui_native_recovery import NativeRecovery
from .gui_normalization_transport import NormalizationTransport


class NativeNormalizationTransport(NormalizationTransport):
    def __init__(self, request, rules):
        super().__init__(request)
        self.incoming = NativeInput(request)
        self.recovery = NativeRecovery(request, rules)

    def output_schema(self, schema):
        result = deepcopy(schema)
        result["properties"]["facts"]["minItems"] = 1
        for name, definition in result.get("$defs", {}).items():
            properties = definition.get("properties", {})
            if name == "GuiFactProposal":
                properties["literalEvidence"]["minItems"] = 1
            if name == "TextValue":
                properties["text"]["minLength"] = 1
        return result

    def encode(self, text):
        if "\n\nRequest payload:\n" in text and not text.startswith("{"):
            return text
        payload = json.loads(super().encode(text))
        instruction = payload.pop("instruction")
        # Give the CLI a direct task before its captured JSON data and constraints.
        return instruction + "\n\nRequest payload:\n" + json.dumps(payload, ensure_ascii=False,
            allow_nan=False, separators=(",", ":"))

    def bind_guard(self, guard):
        self.guard = self.incoming.guard = self.recovery.guard = guard

    @property
    def unresolved(self):
        return self.incoming.unresolved + self.recovery.unresolved

    def decode(self, value):
        return self.incoming.parse(value)

    def restore(self, proposal):
        return self.recovery.recover(super().restore(proposal))
