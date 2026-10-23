"""Keep unchanged block evidence in guards rather than retained inverse bytes."""

from .canonical_patch import apply_patch, build_patch, tokens
from .models.template_mutations import AuthoredBlockHistoryDelta
from .models.canonical_patch import CanonicalPatchV1
from .templates.compiler import canonical, sha256


SYNCED = 'syncedFactRevision'


def block_payload(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json', by_alias=True)
    return {key: item for key, item in value.items() if key not in {'children', 'revision'}}


def authored(value):
    """Authored content only: a field's synced fact revision is bookkeeping that Undo itself advances."""
    if isinstance(value, dict):
        return {key: authored(item) for key, item in value.items() if key != SYNCED}
    if isinstance(value, list):
        return [authored(item) for item in value]
    return value


def semantic_payload(value):
    return authored(block_payload(value))


def block_hash(value):
    return sha256(canonical(semantic_payload(value)))


def block_patch(before, after):
    return build_patch(semantic_payload(before), semantic_payload(after))


def block_delta(before, after):
    old, new = semantic_payload(before), semantic_payload(after)
    return AuthoredBlockHistoryDelta(blockId=old['id'], beforeSemanticHash=sha256(canonical(old)),
        afterSemanticHash=sha256(canonical(new)), forwardPatch=build_patch(old, new), inversePatch=build_patch(new, old))


def resynced(value, current):
    """Restored fields keep the current synced revision of the same fragment; mutation apply resynchronizes them."""
    if isinstance(value, dict):
        result = {key: resynced(item, current) for key, item in value.items()}
        if result.get('type') == 'fact_field':
            result[SYNCED] = current.get(result.get('bindingId'), 1)
        return result
    if isinstance(value, list):
        return [resynced(item, current) for item in value]
    return value


def synced_revisions(value, result=None):
    result = {} if result is None else result
    if isinstance(value, dict):
        if value.get('type') == 'fact_field' and SYNCED in value:
            result.setdefault(value.get('bindingId'), value[SYNCED])
        for item in value.values():
            synced_revisions(item, result)
    elif isinstance(value, list):
        for item in value:
            synced_revisions(item, result)
    return result


def restore_payload(current, expected, resulting, patch):
    patch = CanonicalPatchV1(schemaVersion=1, steps=patch).steps
    full = block_payload(current)
    payload = authored(full)
    if sha256(canonical(payload)) != expected:
        raise ValueError('authored block history preimage changed')
    for step in patch:
        if tokens(step.pointer)[0] in {'id', 'revision', 'children', 'placement'}:
            raise ValueError('authored block patch replaces guarded identity or placement')
    restored = apply_patch(payload, patch)
    if not isinstance(restored, dict) or sha256(canonical(restored)) != resulting:
        raise ValueError('authored block history result mismatch')
    return resynced(restored, synced_revisions(full))
