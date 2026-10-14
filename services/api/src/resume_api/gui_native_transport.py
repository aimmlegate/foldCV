"""Native-only tolerant decoding around the strict normalization transport."""

import json

from .gui_native_input import NativeInput
from .gui_native_recovery import NativeRecovery
from .gui_normalization_transport import NormalizationTransport


class NativeNormalizationTransport(NormalizationTransport):
    def __init__(self, request, rules):
        super().__init__(request)
        self.incoming = NativeInput(request)
        self.recovery = NativeRecovery(request, rules)

    def encode(self, text):
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
