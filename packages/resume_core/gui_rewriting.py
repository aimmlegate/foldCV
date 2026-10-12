"""Scoped rewrite inputs and atomic replacement of validated UTF-16 spans."""

from pydantic import Field

from .gui_derived import digest
from .gui_mutations import checkpoint, complete_session, document_content, records, unicode_valid
from .gui_normalization import public_context_facts
from .gui_legacy_context import public_workspace_facts
from .gui_projection import compatibility_views
from .gui_prompts import content_input
from .gui_refresh import refresh
from .gui_selection import field_index, normalized_text, utf16_slice, valid_selection
from .gui_source_context import source_context
from .models.contracts import Id, Revision, Sha256, Wire
from .models.recovery import Document, MutationResult, Selection, SourceContextRequest
from .privacy import private_output_text


class GuiRewriteRequest(Wire):
    client_request_id: Id
    selection: Selection
    instruction: str = Field(min_length=1, max_length=2000)
    rules_revision: Revision
    rules_sha256: Sha256


class SpanReplacement(Wire):
    field_id: Id
    text: str = Field(max_length=12000)


class GuiRewriteProposal(Wire):
    replacements: list[SpanReplacement] = Field(min_length=1, max_length=1000)


def rewrite_fingerprint(request):
    unicode_valid(request.model_dump())
    return digest(request.model_dump(mode="json", by_alias=True))


def rewriting_input(workspace, request, rules):
    if not valid_selection(workspace, request.selection):
        raise ValueError("SELECTION_STALE")
    if (request.rules_revision, request.rules_sha256) != (rules.revision, rules.sha256):
        raise ValueError("RULES_CHANGED")
    indexed = field_index(workspace.project.document)
    selected = [indexed[span.field_id][0] for span in request.selection.spans]
    ids = {id for field in selected for id in field.fact_ids}
    facts = [fact for fact in public_workspace_facts(workspace) if fact.id in ids
             and not private_output_text(fact.model_dump_json(by_alias=True))]
    context = source_context(workspace, SourceContextRequest(projectId=workspace.project_id,
        documentRevision=workspace.document_revision, selection=request.selection, fieldIds=[]))
    fields = [{"fieldId": span.field_id, "range": span.range.model_dump(),
               "capturedText": span.captured_text, "currentFieldText": indexed[span.field_id][0].text}
              for span in request.selection.spans]
    if any(private_output_text(field["currentFieldText"]) for field in fields) or private_output_text(request.instruction):
        raise ValueError("NO_SAFE_CONTENT")
    return content_input("rewrite_prose", {"selection": fields, "instruction": request.instruction,
        "facts": [fact.model_dump(mode="json", by_alias=True, exclude={"evidence"}) for fact in facts],
        "excerpts": [item.model_dump(mode="json", by_alias=True) for item in context.excerpts
                     if not private_output_text(item.evidence.text)],
        "authoredTextPolicy": "Current authored text is authoritative. Preserve additions and omissions. Replace only each captured span; never restore removed material from evidence."}, rules)


def validate_replacements(selection, proposal):
    if [item.field_id for item in proposal.replacements] != [span.field_id for span in selection.spans]:
        raise ValueError("REWRITE_SCOPE_INVALID")
    for item in proposal.replacements:
        item.text = normalized_text(item.text)
        item.text.encode("utf-8", "strict")
        if private_output_text(item.text):
            raise ValueError("NO_SAFE_CONTENT")
    return proposal


def apply_rewrite(workspace, request, proposal, captured_project_revision, updated_at):
    if workspace.project_revision != captured_project_revision or not valid_selection(workspace, request.selection):
        return MutationResult(status="stale", projectRevision=workspace.project_revision,
            documentRevision=workspace.document_revision, changedSlotIds=[], rejectionReason="SELECTION_STALE", persistence="memory")
    validate_replacements(request.selection, proposal)
    candidate = workspace.model_copy(deep=True)
    indexed = field_index(candidate.project.document)
    slots = list(dict.fromkeys(indexed[span.field_id][1] for span in request.selection.spans))
    before = {slot: checkpoint(candidate, slot) for slot in slots}
    for slot in slots:
        complete_session(candidate, slot)
    changed = []
    for span, replacement in zip(request.selection.spans, proposal.replacements, strict=True):
        field, slot = indexed[span.field_id]
        length = len(field.text.encode("utf-16-le")) // 2
        text = utf16_slice(field.text, 0, span.range.start) + replacement.text + utf16_slice(field.text, span.range.end, length)
        if text != field.text:
            field.text, field.origin, field.fact_ids, field.evidence = text, "user", [], []
            if slot not in changed:
                changed.append(slot)
    Document.model_validate(candidate.project.document.model_dump(by_alias=True))
    if document_content(candidate.project.document) != document_content(workspace.project.document):
        for slot in changed:
            records(candidate)[slot].revision += 1
            candidate.undo_slots[slot] = before[slot]
        candidate.project_revision += 1
        candidate.document_revision += 1
        candidate.project.revision = candidate.project_revision
        candidate.updated_at = updated_at
        candidate.project.views = compatibility_views(candidate.project.document, candidate.project.facts)
        refresh(candidate, changed)
    for name in ("project_revision", "document_revision", "updated_at", "undo_slots", "edit_sessions", "annotations", "derived_state"):
        setattr(workspace, name, getattr(candidate, name))
    for name in ("document", "revision", "views"):
        setattr(workspace.project, name, getattr(candidate.project, name))
    return MutationResult(status="applied", projectRevision=workspace.project_revision,
        documentRevision=workspace.document_revision, changedSlotIds=changed, rejectionReason=None, persistence="memory")


GUI_REWRITE_CONTRACTS = {"gui_rewrite_request": GuiRewriteRequest, "gui_rewrite_proposal": GuiRewriteProposal}
