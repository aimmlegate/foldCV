"""Canonical JSON bytes and SHA-256 hex digests: the identities of packages, documents, facts and captures."""

from __future__ import annotations

import hashlib
import json


def canonical(value) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    def wire(item):
        if hasattr(item, 'model_dump'):
            return item.model_dump(mode='json', by_alias=True)
        if isinstance(item, dict):
            return {key: wire(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [wire(child) for child in item]
        return item
    return sha256(canonical(wire(value)))
