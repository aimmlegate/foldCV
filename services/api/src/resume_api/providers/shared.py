"""Pieces both CLI content providers use: strict JSON parsing, usage sums, the model and plan name checks."""

from __future__ import annotations

import json
import math
import re

from .content import ContentFailure, ReportedUsage


MODEL = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")


PLAN = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")


MAX_SCHEMA = 65_536


MAX_RESULT = 65_536


MAX_DEPTH = 32


REPAIR_FEEDBACK = "The completed response was invalid JSON or did not match the schema. Return only a valid JSON object matching the schema."


# The whole system prompt of a content call on either CLI: it replaces Claude Code's and Codex's own (D155).
SYSTEM_PROMPT = ("Follow the user's instructions exactly. Return the result only through the structured "
                 "output; do not add commentary.")


def strict_json(raw: bytes | str, *, max_bytes: int = MAX_RESULT) -> object:
    try:
        if isinstance(raw, bytes):
            if len(raw) > max_bytes:
                raise ValueError()
            text = raw.decode("utf-8", "strict")
        else:
            text = raw
            if len(text.encode("utf-8", "strict")) > max_bytes:
                raise ValueError()

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            value: dict[str, object] = {}
            for key, item in items:
                if key in value:
                    raise ValueError()
                value[key] = item
            return value

        def number(value: str) -> float:
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError()
            return parsed

        value = json.loads(text, object_pairs_hook=pairs, parse_float=number,
                           parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))

        def inspect(item: object, depth: int) -> None:
            if depth > MAX_DEPTH:
                raise ValueError()
            if isinstance(item, str):
                item.encode("utf-8", "strict")
            elif isinstance(item, list):
                for part in item:
                    inspect(part, depth + 1)
            elif isinstance(item, dict):
                for key, part in item.items():
                    inspect(key, depth + 1)
                    inspect(part, depth + 1)

        inspect(value, 0)
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise ContentFailure("INVALID_RESULT") from None


def _combine(usages: list[ReportedUsage]) -> ReportedUsage:
    def total(name: str) -> int | None:
        values = [getattr(usage, name) for usage in usages]
        known = [value for value in values if value is not None]
        return sum(known) if known else None

    return ReportedUsage(total("input_tokens"), total("cached_input_tokens"),
                         total("output_tokens"), bool(usages) and all(u.complete for u in usages))


class InvalidFinal(ContentFailure):
    def __init__(self):
        super().__init__("INVALID_RESULT")
