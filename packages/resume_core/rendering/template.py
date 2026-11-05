"""The failure a renderer raises, with a public code and optional location details."""

from __future__ import annotations


class RenderFailure(Exception):
    def __init__(self, code: str, details: dict | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}
