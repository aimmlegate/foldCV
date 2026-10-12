"""Apply one stored related suggestion without a second semantic assessment."""

from .gui_mutations import MutationFailure, checkpoint, complete_session, records, unicode_valid
from .gui_normalization import public_context_facts, source_fingerprint
from .gui_selection import field_index, normalized_text, selection_fingerprint, utf16_slice
from .privacy import private_output_text
from .models.recovery import NameAssessmentFact


def apply_related(workspace, payload, rules_sha256=None):
    suggestion = next((item for item in workspace.related_update_suggestions if item.id == payload.suggestion_id), None)
    if suggestion is None: raise MutationFailure('RELATED_UPDATE_STALE')
    deps = suggestion.dependencies
    if (deps != payload.dependencies or (deps.project_revision, deps.document_revision) !=
        (workspace.project_revision, workspace.document_revision) or
        deps.source_fingerprint != source_fingerprint(workspace.project.sources) or
        deps.dependency_fingerprint != selection_fingerprint(workspace) or
        rules_sha256 is not None and deps.rules_sha256 != rules_sha256):
        raise MutationFailure('RELATED_UPDATE_STALE')
    unicode_valid(suggestion.model_dump())
    indexed = field_index(workspace.project.document)
    public = {fact.id for fact in public_context_facts(workspace.project.facts)}
    public.update(fact.id for fact in workspace.project.facts if isinstance(fact, NameAssessmentFact))
    if not set(suggestion.fact_ids) <= public or not suggestion.replacements or len(suggestion.replacements) > 100:
        raise MutationFailure('RELATED_UPDATE_INVALID')
    ids = [replacement.field_id for replacement in suggestion.replacements]
    if len(ids) != len(set(ids)) or not set(ids) <= indexed.keys(): raise MutationFailure('RELATED_UPDATE_INVALID')
    replacements = []
    try:
        for replacement in suggestion.replacements:
            field, slot = indexed[replacement.field_id]
            text = normalized_text(replacement.text)
            if len(text) > 12000 or private_output_text(text): raise MutationFailure('RELATED_UPDATE_INVALID')
            if replacement.range:
                size = len(field.text.encode('utf-16-le')) // 2
                text = utf16_slice(field.text, 0, replacement.range.start) + text + utf16_slice(field.text, replacement.range.end, size)
            if text != field.text: replacements.append((field, slot, text, replacement.range))
    except (UnicodeError, ValueError):
        raise MutationFailure('RELATED_UPDATE_INVALID') from None
    changed = list(dict.fromkeys(slot for _field, slot, _text, _range in replacements))
    if not changed: return []
    before = {slot: checkpoint(workspace, slot) for slot in changed}
    for slot in changed: complete_session(workspace, slot)
    for field, _slot, text, range in replacements:
        field.text, field.origin, field.evidence = text, 'user', []
        field.fact_ids = list(dict.fromkeys([*(field.fact_ids if range else []), *suggestion.fact_ids]))
    for slot in changed:
        records(workspace)[slot].revision += 1
        workspace.undo_slots[slot] = before[slot]
    workspace.annotations = [mark for mark in workspace.annotations if mark.update_suggestion_id != suggestion.id]
    workspace.related_update_suggestions = [item for item in workspace.related_update_suggestions if item.id != suggestion.id]
    return changed
