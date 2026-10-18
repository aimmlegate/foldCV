"""Compile model operations into one validated, unpublished rich transaction."""

from __future__ import annotations

from pydantic import TypeAdapter

from .agent_store import AgentFailure, digest, identity
from .models.agent import AgentAnchor, AgentEditBatch, AgentPrepareResult
from .models.rich_document import FactFieldSpan, Hyperlink, RichBlock, StyledText
from .models.rich_facts import RichFact
from .models.rich_mutations import (
    ActionCapture, MoveBlock, PutBlock, PutRecord, RemoveBlock, RemoveRecord, ReplaceInlineRange, RichMutation,
)
from .rich_assembly import field
from .rich_dependencies import dependencies_current, placements
from .rich_fields import inline_groups, occurrences, working_field
from .rich_mutations import apply_rich_mutation, cut_inline, inline_text, locate, mutation_sha256, parent_items, subtree, utf16_slice
from .rich_panel import new_record, period as new_period
from .rich_sync import RichCompletionRequest, exact_completion, linked_field_steps, selection_checksum, selection_parts


def semantic(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {key: semantic(part) for key, part in value.items() if key not in {"revision", "syncedFactRevision"}}
    if isinstance(value, list):
        return [semantic(part) for part in value]
    return value


def text_of(content):
    return "".join(inline_text(span) for span in content)


def evidence_valid(workspace, evidence, message):
    records = {record.id for record in workspace.project.facts.records}
    units = {(source.id, unit.id) for source in workspace.project.sources for unit in source.units}
    for item in evidence:
        if item.kind == "source" and (item.source_id, item.unit_id) not in units:
            raise AgentFailure("AGENT_EVIDENCE_INVALID")
        if item.kind == "fact" and item.record_id not in records:
            raise AgentFailure("AGENT_EVIDENCE_INVALID")
        if item.kind == "user_correction" and item.quote not in message:
            raise AgentFailure("AGENT_EVIDENCE_INVALID")


def assign_value(target, value):
    return type(target).model_validate({"value": value.value.model_dump(by_alias=True) if hasattr(value.value, "model_dump") else value.value,
        "rawText": value.text, "status": "known" if value.status == "known" else "unresolved",
        "revision": target.revision, "pendingRawText": None, "userCorrected": True})


class Scope:
    def __init__(self, workspace, scope):
        self.whole = scope.kind == "resume"
        self.ranges, self.complete = {}, set()
        self.workspace = workspace
        if not self.whole:
            if not dependencies_current(workspace, scope.selection.capture.dependencies):
                raise AgentFailure("AGENT_STALE_READ")
            if selection_checksum(parts := selection_parts(workspace, scope.selection)) != scope.selection.text_sha256:
                raise AgentFailure("AGENT_STALE_READ")
            for block, start, end, field_name, cell, _ in parts:
                key = (block.id, cell.id if cell else None, field_name)
                self.ranges[key] = (start, end)
                if start is None:
                    self.complete.update(node.id for node in subtree(block))

    def range(self, block_id, cell_id, field_name, start, end):
        if self.whole or block_id in self.complete:
            return
        allowed = self.ranges.get((block_id, cell_id, field_name))
        if allowed is None or not allowed[0] <= start <= end <= allowed[1]:
            raise AgentFailure("AGENT_SCOPE_INVALID")

    def block(self, block):
        if not self.whole and not {node.id for node in subtree(block)} <= self.complete:
            raise AgentFailure("AGENT_SCOPE_INVALID")

    def destination(self, document, parent_id, after_id):
        if self.whole:
            return
        siblings, _ = parent_items(document, parent_id)
        selected = [block.id for block in siblings if block.id in self.complete]
        if not selected or after_id not in selected and not (after_id is None and siblings[0].id in self.complete):
            raise AgentFailure("AGENT_SCOPE_INVALID")

    def record(self, record_id):
        if self.whole:
            return
        for block in self.workspace.project.document.blocks():
            if block.id not in self.complete and not any(key[0] == block.id for key in self.ranges):
                continue
            references = {getattr(link, "record_id", None) for link in block.provenance}
            references.update(getattr(span, "record_id", None) for _, content in inline_groups(block) for span in content)
            references.add(placements(self.workspace.project.document)[block.id][2])
            if record_id in references:
                return
        raise AgentFailure("AGENT_SCOPE_INVALID")

    def allowed_bindings(self):
        result = set()
        for block in self.workspace.project.document.blocks():
            for container, content in inline_groups(block):
                offset = 0
                for span in content:
                    length = len(inline_text(span).encode("utf-16-le")) // 2
                    if isinstance(span, FactFieldSpan):
                        try:
                            self.range(block.id, None if container in {"content", "caption"} else container,
                                "caption" if container == "caption" else "content", offset, offset + length)
                            result.add(span.binding_root_id or span.binding_id)
                        except AgentFailure:
                            pass
                    offset += length
        return result


def require_block(book, snapshot_id, identifier, cell_id=None):
    capture = book.require(snapshot_id, kind="document")
    if capture.query.ids and identifier not in capture.query.ids and cell_id not in capture.query.ids:
        raise AgentFailure("AGENT_SCOPE_INVALID")
    found = locate(capture.workspace.project.document, identifier)
    if found is None:
        raise AgentFailure("AGENT_STALE_READ")
    return found[0][found[1]]


def require_record(book, snapshot_id, identifier):
    capture = book.require(snapshot_id, kind="facts", identifier=identifier)
    record = next((record for record in capture.workspace.project.facts.records if record.id == identifier), None)
    if record is None:
        raise AgentFailure("AGENT_STALE_READ")
    return record


def replacement(content, start, end, additions):
    selected = cut_inline(content, start, end)
    templates = [span for span in selected if inline_text(span)]
    template = templates[0] if templates else content[0] if content else StyledText(type="text", text="", styles={})
    same_field = templates and all(isinstance(span, FactFieldSpan) and isinstance(template, FactFieldSpan)
        and (span.record_id, span.field_key, span.binding_root_id or span.binding_id) ==
            (template.record_id, template.field_key, template.binding_root_id or template.binding_id) for span in templates)
    result = []
    for addition in additions:
        style = (template.content[0].styles if isinstance(template, Hyperlink) and template.content else template.styles
            if not isinstance(template, Hyperlink) else StyledText(type="text", text="", styles={}).styles).model_copy(deep=True)
        if addition.marks:
            for name in ("bold", "italic", "underline", "strike", "code"):
                setattr(style, name, name in addition.marks)
        if same_field:
            span = template.model_copy(deep=True)
            span.binding_root_id = template.binding_root_id or template.binding_id
            span.binding_id, span.text, span.styles = identity("binding"), addition.text, style
        elif len(templates) == 1 and isinstance(template, Hyperlink):
            span = Hyperlink(type="link", href=template.href, content=[StyledText(type="text", text=addition.text, styles=style)])
        else:
            span = StyledText(type="text", text=addition.text, styles=style)
        result.append(span)
    return result


def validate_references(workspace):
    records = {record.id: record for record in workspace.project.facts.records}
    for record in records.values():
        job, subproject = getattr(record, "job_id", None), getattr(record, "subproject_id", None)
        if job is not None and (job not in records or records[job].kind != "employment"):
            raise AgentFailure("AGENT_EDIT_INVALID")
        if subproject is not None and (subproject not in records or records[subproject].kind != "subproject" or records[subproject].job_id != job):
            raise AgentFailure("AGENT_EDIT_INVALID")
    for block in workspace.project.document.blocks():
        for _, content in inline_groups(block):
            for span in content:
                if isinstance(span, FactFieldSpan) and (span.record_id not in records or working_field(records[span.record_id], span.field_key) is None):
                    raise AgentFailure("AGENT_EDIT_INVALID")
        for link in block.provenance:
            record_id = getattr(link, "record_id", None)
            if record_id is not None and record_id not in records:
                raise AgentFailure("AGENT_EDIT_INVALID")


def compile_batch(workspace, run, journal, request, book, session_id):
    scope = Scope(workspace, run.scope)
    document = workspace.project.document
    blocks = {block.id: block for block in document.blocks()}
    records = {record.id: record for record in workspace.project.facts.records}
    steps, edited, removed, symbols, read_ids, write_blocks, moved = [], {}, set(), {}, set(), set(), set()
    new_parents, text_blocks, ranges = {}, set(), {}
    allowed_bindings = scope.allowed_bindings()
    batch_id, action_id = identity("batch"), session_id + ":agent:" + identity("action")

    def structural_anchor(anchor):
        capture = book.require(anchor.snapshot_id)
        parent_id, after_id = symbols.get(anchor.parent_id, anchor.parent_id), symbols.get(anchor.after_id, anchor.after_id)
        if capture.query.kind not in {"context", "document"}:
            raise AgentFailure("AGENT_SCOPE_INVALID")
        if anchor.parent_id in symbols:
            siblings = []
        else:
            parent_items(capture.workspace.project.document, anchor.parent_id)
            if capture.query.kind == "document" and capture.query.ids and anchor.parent_id not in capture.query.ids:
                raise AgentFailure("AGENT_SCOPE_INVALID")
            siblings, _ = parent_items(document, parent_id)
        if after_id is not None and after_id not in {block.id for block in siblings} and after_id not in symbols.values():
            raise AgentFailure("AGENT_EDIT_INVALID")
        if parent_id not in symbols.values():
            scope.destination(document, parent_id, after_id)
        if after_id in new_parents and new_parents[after_id] != parent_id:
            raise AgentFailure("AGENT_EDIT_INVALID")
        read_ids.add(anchor.snapshot_id)
        return parent_id, after_id

    for operation in request.operations:
        if operation.kind == "format_template":
            capture = book.require(operation.snapshot_id, kind="document")
            if not scope.whole or capture.query.ids or len(request.operations) != 1:
                raise AgentFailure("AGENT_SCOPE_INVALID")
            from .rich_format import format_steps
            steps.extend(format_steps(document, workspace.project.facts))
            write_blocks.update(blocks)
            read_ids.add(operation.snapshot_id)
        elif operation.kind in {"insert_table", "insert_asset"}:
            parent_id, after_id = structural_anchor(operation.destination)
            if operation.kind == "insert_table":
                columns = len(operation.rows[0])
                if not 0 < columns <= 20 or any(len(row) != columns or any(len(text) > 16000 for text in row) for row in operation.rows):
                    raise AgentFailure("AGENT_EDIT_INVALID")
                value = {"type": "table", "props": {}, "content": {"columnWidths": [None] * columns,
                    "headerRows": operation.header_rows, "rows": [{"id": identity("row"), "cells": [
                        {"id": identity("cell"), "revision": 1, "content": [{"type": "text", "text": text, "styles": {}}]}
                        for text in row]} for row in operation.rows]}}
            else:
                if not any(asset.id == operation.asset_id for asset in workspace.project.assets):
                    raise AgentFailure("AGENT_NOT_FOUND")
                value = {"type": "image", "content": None, "props": {"assetId": operation.asset_id, "alt": operation.alt,
                    "caption": [], "width": operation.width, "height": operation.height, "alignment": "left"}}
            block = TypeAdapter(RichBlock).validate_python({**value, "id": identity("block"), "revision": 1,
                "children": [], "provenance": []})
            steps.append(PutBlock(kind="put_block", parentId=parent_id, afterId=after_id, beforeRevision=None, block=block))
            write_blocks.add(block.id)
        elif operation.kind == "replace_text":
            target = operation.target
            original = require_block(book, target.snapshot_id, target.block_id, target.cell_id)
            if target.cell_id is not None:
                original = blocks[target.block_id]
            groups = dict(inline_groups(original))
            content = groups.get(target.cell_id or target.field)
            if content is None or target.field == "caption" and target.cell_id is not None:
                raise AgentFailure("AGENT_EDIT_INVALID")
            length = len(text_of(content).encode("utf-16-le")) // 2
            if target.end > length:
                raise AgentFailure("AGENT_EDIT_INVALID")
            utf16_slice(text_of(content), target.start, target.end)
            scope.range(original.id, target.cell_id, target.field, target.start, target.end)
            value = replacement(content, target.start, target.end, operation.content)
            key = (original.id, target.cell_id, target.field)
            if any(not (target.end <= start or target.start >= end) or target.start == target.end == start == end
                    for start, end in ranges.get(key, [])):
                raise AgentFailure("AGENT_EDIT_INVALID")
            ranges.setdefault(key, []).append((target.start, target.end))
            if utf16_slice(text_of(content), target.start, target.end) == text_of(value) and not any(part.marks for part in operation.content):
                read_ids.add(target.snapshot_id)
                continue
            steps.append(ReplaceInlineRange(kind="replace_inline_range", blockId=original.id, cellId=target.cell_id,
                field=target.field, start=target.start, end=target.end, beforeRevision=original.revision, content=value))
            write_blocks.add(original.id); text_blocks.add(original.id); read_ids.add(target.snapshot_id)
        elif operation.kind == "insert_blocks":
            parent_id, after_id = structural_anchor(operation.destination)
            inherited = parent_id
            while inherited in new_parents:
                inherited = new_parents[inherited]
            owner = placements(document).get(inherited, (None, None, None))[2]
            for new in operation.blocks:
                if new.key in symbols or new.key in blocks or new.key in records:
                    raise AgentFailure("AGENT_EDIT_INVALID")
                block_id = symbols[new.key] = identity("block")
                new_parents[block_id] = parent_id
                block = TypeAdapter(RichBlock).validate_python({"id": block_id, "revision": 1,
                    "type": {"bullet_list_item": "bullet_list", "numbered_list_item": "numbered_list"}.get(new.kind, new.kind),
                    "props": {"level": new.level} if new.kind == "heading" else {"recordId": None} if new.kind == "section" else {},
                    "children": [], "content": [{"type": "text", "text": part.text,
                        "styles": {name: True for name in part.marks}} for part in new.content],
                    "provenance": [{"kind": "working_owner", "id": identity("owner"), "recordId": owner}] if owner else []})
                steps.append(PutBlock(kind="put_block", parentId=parent_id, afterId=after_id, beforeRevision=None, block=block))
                write_blocks.add(block_id)
                after_id = block_id
        elif operation.kind in {"delete_blocks", "move_blocks"}:
            parent_id, after_id = structural_anchor(operation.destination) if operation.kind == "move_blocks" else (None, None)
            for identifier in operation.block_ids:
                original = require_block(book, operation.snapshot_id, identifier)
                scope.block(original)
                if operation.kind == "delete_blocks":
                    steps.append(RemoveBlock(kind="remove_block", blockId=identifier, beforeRevision=original.revision))
                else:
                    steps.append(MoveBlock(kind="move_block", blockId=identifier, beforeRevision=original.revision,
                        parentId=parent_id, afterId=after_id))
                    moved.update(node.id for node in subtree(original)); after_id = identifier
                write_blocks.update(node.id for node in subtree(original)); read_ids.add(operation.snapshot_id)
        elif operation.kind == "update_fact":
            original = require_record(book, operation.snapshot_id, operation.record_id)
            scope.record(original.id)
            evidence_valid(workspace, operation.evidence, journal.request.message)
            record = edited.setdefault(original.id, original.model_copy(deep=True))
            key = ("period:" + operation.period_id + ":" + operation.field_key if operation.period_id else operation.field_key)
            if (operation.field_key in {"start", "end", "present"}) != (operation.period_id is not None):
                raise AgentFailure("AGENT_EDIT_INVALID")
            target = working_field(record, key)
            if key == "label" and record.kind == "detail" and operation.value.status == "known" and isinstance(operation.value.value, str):
                record.label = operation.value.value
                read_ids.add(operation.snapshot_id)
                continue
            if target is None:
                raise AgentFailure("AGENT_EDIT_INVALID")
            changed = assign_value(target, operation.value)
            for name in type(target).model_fields:
                setattr(target, name, getattr(changed, name))
            record.user_corrected = True
            read_ids.add(operation.snapshot_id)
        elif operation.kind == "create_fact":
            evidence_valid(workspace, [operation.correction], journal.request.message)
            if operation.key in symbols or operation.key in records or operation.key in blocks:
                raise AgentFailure("AGENT_EDIT_INVALID")
            owner = symbols.get(operation.owner_record_id, operation.owner_record_id)
            available = {**records, **edited}
            if owner is not None and (owner not in available or available[owner].kind not in {"employment", "subproject"}):
                raise AgentFailure("AGENT_EDIT_INVALID")
            if not scope.whole:
                if owner is None:
                    raise AgentFailure("AGENT_SCOPE_INVALID")
                scope.record(owner)
            if operation.record_kind in {"candidate", "employment", "technology", "education", "language"}:
                if operation.record_kind == "candidate" and any(record.kind == "candidate" for record in available.values()):
                    raise AgentFailure("AGENT_EDIT_INVALID")
                record = new_record(operation.record_kind, owner)
            else:
                values = {"name": field(None), "issuer": field(None), "date": field(None)} if operation.record_kind == "certification" else (
                    {"detailType": "other", "label": "", "value": field(None)} if operation.record_kind == "detail" else
                    {"jobId": owner, "subprojectId": None, "value": field(None)})
                record = TypeAdapter(RichFact).validate_python({"id": identity("fact"), "kind": operation.record_kind,
                    "revision": 1, "origin": "user", "evidence": [], "userCorrected": True, **values})
            if owner is not None and available[owner].kind == "subproject" and hasattr(record, "job_id"):
                record.job_id, record.subproject_id = available[owner].job_id, owner
            for key, value in operation.values.items():
                target = working_field(record, key)
                if key == "label" and record.kind == "detail" and value.status == "known" and isinstance(value.value, str):
                    record.label = value.value
                    continue
                if target is None:
                    raise AgentFailure("AGENT_EDIT_INVALID")
                setattr(record, key, assign_value(target, value))
            if operation.periods:
                if record.kind != "employment":
                    raise AgentFailure("AGENT_EDIT_INVALID")
                record.periods = []
                for period in operation.periods:
                    value = new_period()
                    value.id = identity("period")
                    for name in ("start", "end", "present"):
                        setattr(value, name, assign_value(getattr(value, name), getattr(period, name)))
                    record.periods.append(value)
            symbols[operation.key] = record.id
            edited[record.id] = record
        else:
            original = require_record(book, operation.snapshot_id, operation.record_id)
            evidence_valid(workspace, [operation.correction], journal.request.message)
            scope.record(original.id)
            if not scope.whole:
                for group in occurrences(document).values():
                    if group.record_id == original.id and any((span.binding_root_id or span.binding_id) not in allowed_bindings for span in group.spans):
                        raise AgentFailure("AGENT_SCOPE_INVALID")
            removed.add(original.id); read_ids.add(operation.snapshot_id)

    if not read_ids <= {snapshot.id for snapshot in journal.snapshots} or not set(request.snapshot_ids) <= {snapshot.id for snapshot in journal.snapshots}:
        raise AgentFailure("AGENT_STALE_READ")
    if set(edited) & removed:
        raise AgentFailure("AGENT_EDIT_INVALID")
    steps = sorted([step for step in steps if isinstance(step, ReplaceInlineRange)],
        key=lambda step: (step.block_id, step.cell_id or "", -step.start)) + [step for step in steps if not isinstance(step, ReplaceInlineRange)]
    if not steps and not edited and not removed:
        return AgentPrepareResult(disposition="no_change", batchId=None, affected=[], preview=""), None
    dependencies = [dependency for snapshot in journal.snapshots for dependency in snapshot.dependencies]
    unique = {digest(part): part for part in dependencies}
    dependencies = list(unique.values())
    captures = [part.stamp for part in dependencies if part.kind == "entity"]
    captures = list({(part.kind, part.id): part for part in captures}.values())
    capture = ActionCapture(sessionId=session_id, actionId=action_id, actionToken=0, dependencies=captures)
    def mutation_for(parts):
        return RichMutation(schemaVersion=1, projectId=run.project_id, clientMutationId="agent_" + batch_id,
            actionId=action_id, kind="structure", capture=capture, steps=parts)
    def fact_steps():
        return [PutRecord(kind="put_record", beforeRevision=records[key].revision if key in records else None, record=record)
            for key, record in edited.items()] + [RemoveRecord(kind="remove_record", recordId=key, beforeRevision=records[key].revision) for key in removed]
    interim = apply_rich_mutation(workspace, mutation_for(steps + fact_steps()))[0]
    old_groups, new_groups = occurrences(document), occurrences(interim.project.document)
    removed_fields = [{"recordId": group.record_id, "fieldKey": group.key, "rootId": group.root}
        for key, group in old_groups.items() if key not in new_groups and set(group.block_ids) & text_blocks]
    if any(operation.kind == "format_template" for operation in request.operations):
        computed, conflicts = [], []
    else:
        computed, conflicts = exact_completion(interim, RichCompletionRequest(capture=capture,
            blockIds=[key for key in write_blocks if locate(interim.project.document, key)], movedIds=list(moved), removedFields=removed_fields, interpret=False))
    for step in computed:
        if not isinstance(step, PutRecord):
            continue
        key, updated = step.record.id, step.record
        if key in edited and semantic(edited[key]) != semantic(updated):
            raise AgentFailure("AGENT_EDIT_INVALID")
        edited[key] = updated
    for identifier in text_blocks:
        for link in blocks[identifier].provenance:
            if link.kind == "citation" and link.record_id not in edited and link.record_id not in removed:
                record = edited.setdefault(link.record_id, records[link.record_id].model_copy(deep=True))
                for key in link.field_keys:
                    target = working_field(record, key)
                    if target is not None:
                        target.status, target.pending_raw_text = "conflict", None
    interim = apply_rich_mutation(workspace, mutation_for(steps + fact_steps()))[0]
    linked = linked_field_steps(interim, list(edited))
    outside = set()
    for step in linked:
        before = locate(interim.project.document, step.block.id)[0]
        old = next(block for block in before if block.id == step.block.id)
        candidate = step.block.model_copy(deep=True)
        originals = {span.binding_id: span for _, content in inline_groups(old) for span in content if isinstance(span, FactFieldSpan)}
        for _, content in inline_groups(candidate):
            for span in content:
                if isinstance(span, FactFieldSpan) and span.binding_id in originals and not scope.whole and (span.binding_root_id or span.binding_id) not in allowed_bindings:
                    original = originals[span.binding_id]
                    if span.text != original.text:
                        outside.add((span.record_id, span.field_key))
                        span.text, span.synced_fact_revision = original.text, original.synced_fact_revision
        if semantic(candidate) != semantic(old.model_copy(update={"children": []})):
            steps.append(PutBlock(kind="put_block", parentId=step.parent_id, afterId=step.after_id,
                beforeRevision=blocks[candidate.id].revision, block=candidate, keepChildren=True))
            write_blocks.add(candidate.id)
    for record_id, key in [*conflicts, *outside]:
        if record_id in removed:
            continue
        record = edited.setdefault(record_id, records[record_id].model_copy(deep=True))
        target = working_field(record, key)
        if target is not None:
            target.status, target.pending_raw_text = "conflict", None
    mutation = mutation_for(steps + fact_steps())
    candidate = apply_rich_mutation(workspace, mutation)[0]
    validate_references(candidate)
    if semantic(candidate.project.document) == semantic(document) and semantic(candidate.project.facts) == semantic(workspace.project.facts):
        return AgentPrepareResult(disposition="no_change", batchId=None, affected=[], preview=""), None
    # Freeze generated inline identities now; preview and commit must apply identical cells.
    rewritten = {step.block_id for step in mutation.steps if isinstance(step, ReplaceInlineRange)}
    rewritten.update(step.block.id for step in mutation.steps if isinstance(step, PutBlock) and step.keep_children)
    final_blocks = {block.id: block for block in candidate.project.document.blocks()}
    final_places = placements(candidate.project.document)
    if not rewritten <= final_blocks.keys():
        raise AgentFailure("AGENT_EDIT_INVALID")
    canonical = [step for step in mutation.steps if not isinstance(step, ReplaceInlineRange)
        and not (isinstance(step, PutBlock) and step.keep_children)]
    canonical += [PutBlock(kind="put_block", parentId=final_places[key][0], afterId=final_places[key][1],
        beforeRevision=blocks[key].revision, block=final_blocks[key].model_copy(update={"children": []}), keepChildren=True)
        for key in sorted(rewritten)]
    mutation = mutation_for(canonical)
    candidate = apply_rich_mutation(workspace, mutation)[0]
    validate_references(candidate)
    affected = [AgentAnchor(blockId=key, cellId=None, recordId=None, fieldKey=None, start=None, end=None,
        text="", dependencies=[]) for key in sorted(write_blocks)[:100]]
    preview = "Update " + str(len(write_blocks)) + " blocks and " + str(len(edited) + len(removed)) + " facts."
    batch = AgentEditBatch(id=batch_id, runId=run.id, toolKey=request.key, ownerEpoch=run.owner_epoch,
        state="prepared", scope=run.scope, readSnapshotIds=list(dict.fromkeys(snapshot.id for snapshot in journal.snapshots)),
        dependencies=dependencies, mutation=mutation, requestSha256=mutation_sha256(mutation),
        previewSha256=digest([step.model_dump(mode="json", by_alias=True) for step in mutation.steps]),
        affected=affected, affectedCount=len(write_blocks), factRecordIds=list(dict.fromkeys([*edited, *removed])))
    return AgentPrepareResult(disposition="prepared", batchId=batch.id, affected=affected,
        affectedCount=len(write_blocks), preview=preview), batch
