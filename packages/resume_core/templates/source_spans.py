"""Reply pointers into source items: the item root a bound pointer names and the value it points at."""

from __future__ import annotations

from .builtin_mapping import item_root
from .projection import pointer_tokens


def payload_value(payload,pointer):
    value=payload
    for token in pointer_tokens(pointer):
        if isinstance(value,dict) and token in value: value=value[token]
        elif isinstance(value,list) and token.isascii() and token.isdecimal() and (token=='0' or not token.startswith('0')) and int(token)<len(value):
            value=value[int(token)]
        else: raise ValueError("payload pointer does not resolve")
    return value


def _bound_root(pointer, semantic_type, field_key, bindings):
    actual = pointer_tokens(pointer)
    candidates = [binding for binding in bindings if binding.semantic_type == semantic_type and binding.field == field_key
        and len(pointer_tokens(binding.pointer)) == len(actual)
        and all(pattern == '*' or pattern == token for pattern, token in zip(pointer_tokens(binding.pointer), actual, strict=True))]
    if len(candidates) != 1:
        raise ValueError('field has no unique compiled item binding')
    return actual[:len(item_root(candidates[0], bindings))]
