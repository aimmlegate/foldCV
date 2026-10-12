"""Atomic in-memory authored mutations and one checkpoint per block."""

from __future__ import annotations

import hashlib
import json
from pydantic import ValidationError

from .gui_derived import digest
from .gui_projection import compatibility_views
from .gui_selection import field_index, normalized_text
from .models.recovery import (Annotation, BlockCheckpoint, BufferedField, Dependencies, Document,
    EditSession, FactStamp, MutationReplay, MutationResult, SourceExclusion, authored_fields, record_slot)
from .normalization import _id


class MutationFailure(Exception):
    pass


def content(record):
    def authored(value):
        if isinstance(value, list):
            return [authored(item) for item in value]
        if isinstance(value, dict):
            return {key: authored(item) for key, item in value.items()
                    if key not in {"factIds", "evidence", "origin", "revision", "visible"}}
        return value
    return authored(record.model_dump(mode="json", by_alias=True))


def document_content(document):
    return [{"slot": record_slot(record), "visible": record.visible, "content": content(record)}
            for record in document.records()]


def records(workspace):
    return {record_slot(record): record for record in workspace.project.document.records()}


def checkpoint(workspace, slot):
    record = records(workspace)[slot]
    ids = {id for field in authored_fields(record) for id in field.fact_ids}
    facts = [fact.model_copy(deep=True) for fact in workspace.project.facts if fact.id in ids]
    marks = [mark.model_copy(deep=True) for mark in workspace.annotations
             if mark.anchor.kind == "field" and mark.anchor.field_id.split("/", 1)[0] == slot]
    return BlockCheckpoint(record=record.model_copy(deep=True), facts=facts, annotations=marks,
        factStamps=[FactStamp(factId=fact.id, revision=fact.revision, ownerSlotId=slot, origin=fact.origin,
            authoritativeRevision=workspace.document_revision) for fact in facts],
        projectRevision=workspace.project_revision, documentRevision=workspace.document_revision)


def complete_session(workspace, slot):
    session = workspace.edit_sessions.pop(slot, None)
    if session and content(records(workspace)[slot]) != content(session.baseline.record):
        workspace.undo_slots[slot] = session.baseline.model_copy(deep=True)


def replace_record(document, slot, value):
    for name in ("candidate", "profile", "skills_focus", "early_career"):
        if record_slot(getattr(document, name)) == slot:
            setattr(document, name, value)
            return
    for name in ("jobs", "education", "certifications", "languages"):
        collection = getattr(document, name)
        for index, record in enumerate(collection):
            if record_slot(record) == slot:
                collection[index] = value
                return
    raise MutationFailure("TARGET_NOT_FOUND")


def newer_authoritative_mention(workspace, target, slot, fact_id):
    for other_slot, record in records(workspace).items():
        if other_slot == slot:
            continue
        if not any(field.origin == "user" and fact_id in field.fact_ids for field in authored_fields(record)):
            continue
        session = workspace.edit_sessions.get(other_slot)
        previous = session.baseline if session else workspace.undo_slots.get(other_slot)
        if previous and previous.document_revision >= target.document_revision and content(previous.record) != content(record):
            return True
    return False


def restore_facts(workspace, slot, target, previous_record):
    current = {fact.id: fact for fact in workspace.project.facts}
    other_refs = {id for other_slot, record in records(workspace).items() if other_slot != slot
                  for field in authored_fields(record) for id in field.fact_ids}
    previous_ids = {id for field in authored_fields(previous_record) for id in field.fact_ids}
    baseline_ids = {fact.id for fact in target.facts}
    removed = previous_ids - baseline_ids - other_refs
    workspace.project.facts = [fact for fact in workspace.project.facts if fact.id not in removed or fact.origin != "user"]
    conflicts = []
    for previous in target.facts:
        fact = current.get(previous.id)
        if fact is None:
            workspace.project.facts.append(previous.model_copy(deep=True))
        elif fact.model_dump(exclude={"revision"}) != previous.model_dump(exclude={"revision"}):
            if previous.id in other_refs and newer_authoritative_mention(workspace, target, slot, previous.id):
                conflicts.append(previous.id)
            else:
                restored = previous.model_copy(update={"revision": fact.revision + 1}, deep=True)
                workspace.project.facts = [restored if item.id == fact.id else item for item in workspace.project.facts]
    return conflicts


def restore(workspace, payload):
    slot = payload.slot_id
    record = records(workspace).get(slot)
    if record is None:
        raise MutationFailure("TARGET_NOT_FOUND")
    session = workspace.edit_sessions.get(slot)
    if session and payload.session_id not in (None, session.session_id):
        raise MutationFailure("SESSION_MISMATCH")
    changed_buffer = session and content(record) != content(session.baseline.record)
    target = session.baseline if changed_buffer else workspace.undo_slots.get(slot)
    if target is None:
        return []
    previous_content = content(record)
    restored = target.record.model_copy(update={"visible": record.visible,
        "revision": record.revision + int(previous_content != content(target.record))}, deep=True)
    replace_record(workspace.project.document, slot, restored)
    conflicts = restore_facts(workspace, slot, target, record)
    workspace.annotations = [mark for mark in workspace.annotations
        if not (mark.anchor.kind == "field" and mark.anchor.field_id.split("/", 1)[0] == slot)] + [mark.model_copy(deep=True) for mark in target.annotations]
    if not changed_buffer:
        workspace.undo_slots[slot] = None
    if session:
        session.baseline = checkpoint(workspace, slot)
        session.buffered_fields = []
        session.started_document_revision = workspace.document_revision + (previous_content != content(restored))
    if conflicts:
        field = next((field for field in authored_fields(restored) if set(field.fact_ids) & set(conflicts)), authored_fields(restored)[0])
        deps = Dependencies(projectRevision=workspace.project_revision + 1, documentRevision=workspace.document_revision + 1,
            rulesSha256=workspace.rules_used.sha256 if workspace.rules_used else None,
            sourceFingerprint=digest([source.model_dump(mode="json", by_alias=True) for source in workspace.project.sources]),
            dependencyFingerprint=digest({"slot": slot, "conflicts": conflicts, "revision": workspace.document_revision}))
        workspace.annotations.append(Annotation(id=_id("annotation", slot, "shared-restore", str(workspace.document_revision)),
            type="conflicting", code="restore_shared_fact_conflict", anchor={"kind": "field", "fieldId": field.field_id, "range": None},
            dependencies=deps, factIds=conflicts, reason="A newer authoritative mention was retained in another block.",
            evidence=[], resolved=False, updateSuggestionId=None, removedFocus=[]))
    return [slot] if previous_content != content(restored) or conflicts else []


def edit(workspace, payload):
    indexed = field_index(workspace.project.document)
    special = {job.periods_field_id: record_slot(job) for job in workspace.project.document.jobs}
    special[workspace.project.document.skills_focus.focus_field_id] = "skills-focus"
    slot = indexed[payload.field_id][1] if payload.field_id in indexed else special.get(payload.field_id)
    if slot is None:
        raise MutationFailure("TARGET_NOT_FOUND")
    record = records(workspace)[slot]
    before = content(record)
    value = record.model_copy(deep=True)
    if payload.text is not None and payload.field_id in indexed:
        field = next(field for field in authored_fields(value) if field.field_id == payload.field_id)
        text = normalized_text(payload.text)
        text.encode("utf-8")
        if field.text != text:
            field.text, field.origin, field.fact_ids, field.evidence = text, "user", [], []
    elif payload.periods is not None and payload.field_id in special and record.kind == "job":
        value.periods = [period.model_copy(deep=True) for period in payload.periods]
        for period in value.periods:
            for key, field in (("startText", period.start_text), ("endText", period.end_text)):
                if field.field_id != f"{slot}/period:{period.id}/{key}":
                    raise MutationFailure("INVALID_FIELD_IDENTITY")
                original = next((item for item in authored_fields(record) if item.field_id == field.field_id), None)
                if original and original.text == normalized_text(field.text):
                    setattr(period, "start_text" if key == "startText" else "end_text", original.model_copy(deep=True))
                else:
                    field.text, field.origin, field.fact_ids, field.evidence = normalized_text(field.text), "user", [], []
    elif payload.focus is not None and payload.field_id == workspace.project.document.skills_focus.focus_field_id and record.kind == "skills-focus":
        value.focus = [entry.model_copy(deep=True) for entry in payload.focus]
        for entry in value.focus:
            if entry.display.field_id != f"skills-focus/focus:{entry.id}/display":
                raise MutationFailure("INVALID_FIELD_IDENTITY")
            original = next((item for item in record.focus if item.id == entry.id and item.catalog_id == entry.catalog_id), None)
            if original and original.display.text == normalized_text(entry.display.text):
                entry.display, entry.fact_ids = original.display.model_copy(deep=True), original.fact_ids[:]
            else:
                entry.display.text, entry.display.origin, entry.display.fact_ids, entry.display.evidence = normalized_text(entry.display.text), "user", [], []
                entry.fact_ids = []
    else:
        raise MutationFailure("INVALID_EDIT_VALUE")
    session = workspace.edit_sessions.get(slot)
    if session and session.session_id != payload.session_id:
        raise MutationFailure("SESSION_MISMATCH")
    changed = before != content(value)
    if changed:
        if session is None:
            session = EditSession(sessionId=payload.session_id, baseline=checkpoint(workspace, slot),
                bufferedFields=[], startedDocumentRevision=workspace.document_revision)
            workspace.edit_sessions[slot] = session
        value.revision += 1
        replace_record(workspace.project.document, slot, value)
        session.buffered_fields = [BufferedField(fieldId=field.field_id, text=field.text) for field in authored_fields(value)]
    if payload.completion == "slot":
        complete_session(workspace, slot)
    return [slot] if changed else []


def exclusion(workspace, record, reason):
    slot = record_slot(record)
    ids = {id for field in authored_fields(record) for id in field.fact_ids}
    sources = {ref.source_id for fact in workspace.project.facts if fact.id in ids for ref in fact.evidence}
    workspace.source_exclusions = [item for item in workspace.source_exclusions if item.record_id != slot or item.reason != reason]
    workspace.source_exclusions.append(SourceExclusion(id=_id("exclusion", slot, reason), recordId=slot,
        sourceIds=sorted(sources), factIds=sorted(ids), reason=reason, revision=workspace.document_revision + 1))


def structural(workspace, mutation):
    document, payload = workspace.project.document, mutation.payload
    if mutation.kind == "hide":
        record = records(workspace).get(payload.slot_id)
        if record is None:
            raise MutationFailure("TARGET_NOT_FOUND")
        if record.kind == "candidate" and not payload.visible:
            raise MutationFailure("CANDIDATE_REQUIRED")
        if record.visible == payload.visible:
            return []
        complete_session(workspace, payload.slot_id)
        record.visible = payload.visible
        record.revision += 1
        if payload.visible:
            workspace.source_exclusions = [item for item in workspace.source_exclusions if item.record_id != payload.slot_id or item.reason != "hidden"]
        else:
            exclusion(workspace, record, "hidden")
        return [payload.slot_id]
    collection = getattr(document, payload.section_id)
    kinds = {"jobs": "job", "education": "education", "languages": "language"}
    if mutation.kind == "add":
        record = payload.record.model_copy(deep=True)
        slot = record_slot(record)
        if record.kind != kinds[payload.section_id] or slot in records(workspace):
            raise MutationFailure("INVALID_MEMBERSHIP")
        for field in authored_fields(record):
            if not field.field_id.startswith(slot + "/"):
                raise MutationFailure("INVALID_FIELD_IDENTITY")
            field.text, field.origin, field.fact_ids, field.evidence = normalized_text(field.text), "user", [], []
        if record.kind == "job" and record.periods_field_id != slot + "/periods":
            raise MutationFailure("INVALID_FIELD_IDENTITY")
        position = len(collection)
        if payload.after_record_id is not None:
            previous = next((index for index, item in enumerate(collection) if item.id == payload.after_record_id), None)
            if previous is None:
                raise MutationFailure("TARGET_NOT_FOUND")
            position = previous + 1
        collection.insert(position, record)
        workspace.undo_slots[slot] = None
        return [slot]
    if mutation.kind == "delete":
        record = next((item for item in collection if item.id == payload.record_id), None)
        if record is None:
            raise MutationFailure("TARGET_NOT_FOUND")
        slot = record_slot(record)
        exclusion(workspace, record, "deleted")
        collection.remove(record)
        workspace.undo_slots.pop(slot, None)
        workspace.edit_sessions.pop(slot, None)
        workspace.annotations = [mark for mark in workspace.annotations
            if not (mark.anchor.kind == "field" and mark.anchor.field_id.split("/", 1)[0] == slot)]
        return [slot]
    if mutation.kind == "reorder":
        ids = [item.id for item in collection]
        if set(ids) != set(payload.ordered_ids) or len(ids) != len(payload.ordered_ids):
            raise MutationFailure("INVALID_MEMBERSHIP")
        if ids == payload.ordered_ids:
            return []
        ordered = {item.id: item for item in collection}
        setattr(document, payload.section_id, [ordered[id] for id in payload.ordered_ids])
        return [record_slot(ordered[id]) for id in payload.ordered_ids]
    raise MutationFailure("FEATURE_NOT_READY")


def apply_mutation(workspace, mutation, updated_at):
    request = mutation.root
    payload = request.model_dump(mode="json", by_alias=True)
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    def unicode_valid(value):
        if isinstance(value, str):
            value.encode("utf-8")
        elif isinstance(value, list):
            for item in value: unicode_valid(item)
        elif isinstance(value, dict):
            for item in value.values(): unicode_valid(item)
    previous = next((item for item in workspace.mutation_replay if item.client_mutation_id == request.client_mutation_id), None)
    if previous:
        if previous.payload_sha256 != fingerprint:
            return MutationResult(status="rejected", projectRevision=workspace.project_revision,
                documentRevision=workspace.document_revision, changedSlotIds=[], rejectionReason="MUTATION_ID_REUSED", persistence="memory")
        return MutationResult(status="replayed", projectRevision=previous.project_revision,
            documentRevision=previous.document_revision, changedSlotIds=[], rejectionReason=previous.rejection_reason, persistence="memory")
    invalid_unicode = False
    try:
        unicode_valid(payload)
    except UnicodeError:
        invalid_unicode = True
        try:
            request.client_mutation_id.encode("utf-8")
        except UnicodeError:
            return MutationResult(status="rejected", projectRevision=workspace.project_revision,
                documentRevision=workspace.document_revision, changedSlotIds=[], rejectionReason="INVALID_DOCUMENT", persistence="memory")
    result = MutationResult(status="applied", projectRevision=workspace.project_revision,
        documentRevision=workspace.document_revision, changedSlotIds=[], rejectionReason=None, persistence="memory")
    candidate = workspace.model_copy(deep=True)
    if invalid_unicode:
        result.status, result.rejection_reason = "rejected", "INVALID_DOCUMENT"
    elif request.project_id != workspace.project_id:
        result.status, result.rejection_reason = "rejected", "PROJECT_MISMATCH"
    elif request.base_revision != workspace.document_revision:
        result.status, result.rejection_reason = "stale", "DOCUMENT_REVISION_CHANGED"
    elif workspace.project is None:
        result.status, result.rejection_reason = "rejected", "NO_DOCUMENT"
    else:
        try:
            if request.kind == "edit-field": changed = edit(candidate, request.payload)
            elif request.kind == "restore-previous-block": changed = restore(candidate, request.payload)
            elif request.kind == "apply-related-update": raise MutationFailure("FEATURE_NOT_READY")
            else: changed = structural(candidate, request)
            Document.model_validate(candidate.project.document.model_dump(by_alias=True))
            document_changed = document_content(candidate.project.document) != document_content(workspace.project.document)
            facts_changed = candidate.project.facts != workspace.project.facts
            marks_changed = candidate.annotations != workspace.annotations
            metadata_changed = candidate.project.document != workspace.project.document
            if document_changed or facts_changed or marks_changed or metadata_changed:
                candidate.project_revision += 1
                candidate.document_revision += int(document_changed)
                candidate.project.revision = candidate.project_revision
                candidate.derived_state = None
                candidate.updated_at = updated_at
                candidate.project.views = compatibility_views(candidate.project.document, candidate.project.facts)
            if request.kind == "restore-previous-block" and request.payload.slot_id in candidate.edit_sessions:
                session = candidate.edit_sessions[request.payload.slot_id]
                session.baseline = checkpoint(candidate, request.payload.slot_id)
                session.started_document_revision = candidate.document_revision
            result.changed_slot_ids = changed
            result.project_revision, result.document_revision = candidate.project_revision, candidate.document_revision
            # Keep live Generation/Operation objects; their status changes do not replace authored state.
            for field in ("project_revision", "document_revision", "updated_at", "undo_slots", "edit_sessions",
                          "annotations", "derived_state", "source_exclusions"):
                setattr(workspace, field, getattr(candidate, field))
            for field in ("document", "revision", "views", "facts"):
                setattr(workspace.project, field, getattr(candidate.project, field))
        except (MutationFailure, ValidationError, UnicodeError) as error:
            result.status = "rejected"
            result.rejection_reason = str(error) if isinstance(error, MutationFailure) else "INVALID_DOCUMENT"
    workspace.mutation_replay.append(MutationReplay(clientMutationId=request.client_mutation_id, payloadSha256=fingerprint,
        status=result.status, projectRevision=result.project_revision, documentRevision=result.document_revision,
        rejectionReason=result.rejection_reason))
    return result
