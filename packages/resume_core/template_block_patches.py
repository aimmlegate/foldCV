"""Keep unchanged block evidence in guards rather than retained inverse bytes."""

from .canonical_patch import apply_patch, build_patch, tokens
from .models.template_mutations import AuthoredBlockHistoryDelta
from .models.canonical_patch import CanonicalPatchV1
from .templates.compiler import canonical, sha256


def block_payload(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json', by_alias=True)
    return {key: item for key, item in value.items() if key not in {'children', 'revision'}}


def block_hash(value):
    return sha256(canonical(block_payload(value)))


def block_delta(before, after):
    old, new = block_payload(before), block_payload(after)
    return AuthoredBlockHistoryDelta(blockId=old['id'], beforeSemanticHash=sha256(canonical(old)),
        afterSemanticHash=sha256(canonical(new)), forwardPatch=build_patch(old, new), inversePatch=build_patch(new, old))


def restore_payload(current, expected, resulting, patch):
    patch = CanonicalPatchV1(schemaVersion=1, steps=patch).steps
    payload = block_payload(current)
    if sha256(canonical(payload)) != expected:
        raise ValueError('authored block history preimage changed')
    for step in patch:
        if tokens(step.pointer)[0] in {'id', 'revision', 'children', 'placement'}:
            raise ValueError('authored block patch replaces guarded identity or placement')
    restored = apply_patch(payload, patch)
    if not isinstance(restored, dict) or sha256(canonical(restored)) != resulting:
        raise ValueError('authored block history result mismatch')
    return restored
