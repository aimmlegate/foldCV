"""Targeted facts-panel edits and authored document placement."""

from typing import Literal

from pydantic import Field, TypeAdapter, ConfigDict, model_validator

from .models.contracts import Id, Revision, Wire
from .models.rich_document import RichBlock, FactFieldSpan, StyledText
from .models.rich_facts import RichFact, WorkingPeriod
from .models.rich_mutations import ActionCapture, RichMutation, PutRecord, RemoveRecord, PutBlock, RemoveBlock
from .rich_assembly import field, identity
from .rich_dependencies import placements
from .rich_fields import inline_groups, set_text
from .rich_sync import linked_field_steps
from .technology_focus import focus_order_steps, focus_membership_steps
from .technology_lists import (additional_bindings, bind_edit_lists, insert_technology, list_parts, rebuild,
    patch_lists, prune_empty_lists, remove_from_prose)

PanelKind = Literal["candidate", "employment", "technology", "education", "language", "claim"]
FIELDS = {"candidate": ("name", "title", "location"), "employment": ("employer", "role"),
    "technology": ("display", "experience"), "education": ("institution", "qualification", "specialty", "completion"),
    "language": ("language", "level"), "claim": ("value",)}


class RichPanelRequest(Wire):
    model_config = ConfigDict(json_schema_extra={
        "if": {"properties": {"operation": {"const": "clear_technologies"}}, "required": ["operation"]},
        "then": {"properties": {"recordKind": {"const": "technology"}, "recordId": {"type": "null"},
            "periodId": {"type": "null"}, "values": {"maxProperties": 0}}, "required": ["recordKind"]},
        "else": {"if": {"properties": {"operation": {"enum": ["add_to_focus", "remove_from_focus"]}}, "required": ["operation"]},
            "then": {"properties": {"recordId": {"type": "string"}, "recordKind": {"enum": [None, "technology"]},
                "jobId": {"type": "null"}, "periodId": {"type": "null"}, "values": {"maxProperties": 0}}, "required": ["recordId"]}},
    })
    operation: Literal["add", "edit", "remove", "add_period", "remove_period", "clear_technologies", "add_to_focus", "remove_from_focus", "move_technology", "move_focus"]
    record_id: Id | None = None
    record_kind: PanelKind | None = None
    job_id: Id | None = None
    period_id: Id | None = None
    before_record_id: Id | None = Field(default=None, exclude_if=lambda value: value is None)
    values: dict[str, str] = Field(default_factory=dict, max_length=50)
    facts_revision: Revision
    document_revision: Revision
    capture: ActionCapture

    @model_validator(mode="after")
    def operation_scope(self):
        if self.before_record_id is not None and self.operation not in {"move_technology", "move_focus"}:
            raise ValueError("TECHNOLOGY_MOVE_INVALID")
        if self.operation in {"move_technology", "move_focus"} and (self.record_id is None
                or self.record_kind not in {None, "technology"} or self.job_id is not None or self.period_id is not None or self.values):
            raise ValueError("TECHNOLOGY_MOVE_INVALID")
        if self.operation in {"add_to_focus", "remove_from_focus"} and (self.record_id is None
                or self.record_kind not in {None, "technology"} or self.job_id is not None or self.period_id is not None or self.values):
            raise ValueError("FOCUS_SCOPE_INVALID")
        if self.operation == "clear_technologies" and (self.record_kind != "technology" or self.record_id is not None
                or self.period_id is not None or self.values):
            raise ValueError("PANEL_CLEAR_INVALID")
        return self


class RichPanelSyncRequest(Wire):
    capture: ActionCapture
    record_ids: list[Id] = Field(min_length=1, max_length=100)


class NarrativeUpdate(Wire):
    block_id: Id
    cell_id: Id | None = None
    text: str = Field(max_length=16000)


class RichPanelProposal(Wire):
    updates: list[NarrativeUpdate] = Field(max_length=100)
    uncertain: list[Id] = Field(default_factory=list, max_length=100)


def period():
    return WorkingPeriod.model_validate({"id": identity("period"), "revision": 1,
        "start": field(None), "end": field(None), "present": field(False, ""), "evidence": []})


def new_record(kind, job_id=None):
    values = {key: field(None) for key in FIELDS[kind]}
    if kind == "employment":
        values["periods"] = [period().model_dump(by_alias=True)]
    elif kind == "technology":
        values.update(jobId=job_id, subprojectId=None, canonicalId=field(None))
    elif kind == "claim":
        values.update(jobId=None, subprojectId=None)
    return TypeAdapter(RichFact).validate_python({"id": identity(kind), "kind": kind, "revision": 1,
        "origin": "user", "evidence": [], "userCorrected": True, **values})


def field_block(record, key, kind="paragraph", level=1):
    from .rich_fields import working_field
    value = working_field(record, key)
    return {"id": identity("field"), "revision": 1, "type": kind,
        "props": {"level": level} if kind == "heading" else {}, "children": [],
        "content": [{"type": "fact_field", "bindingId": identity("binding"), "recordId": record.id,
            "fieldKey": key, "text": value.raw_text, "styles": {}, "syncedFactRevision": value.revision}],
        "provenance": [{"kind": "field_binding", "id": identity("link"), "recordId": record.id, "fieldKey": key}]}


def record_blocks(record):
    if record.kind == "claim":
        return []
    keys = list(FIELDS[record.kind])
    if record.kind == "technology" and not record.experience.raw_text:
        keys.remove("experience")
    children = [field_block(record, key, "heading" if record.kind == "candidate" and key in {"name", "title"} else "paragraph",
        1 if key == "name" else 2) for key in keys]
    if record.kind == "employment":
        children += [period_block(record, p) for p in record.periods]
    if record.kind == "candidate":
        return children
    if record.kind == "technology":
        return children
    return [{"id": identity("section"), "revision": 1, "type": "section", "props": {"recordId": record.id},
        "content": [], "children": children, "provenance": []}]


def panel_mutation(workspace, request):
    project = workspace.project
    if project is None or (project.facts.revision, project.document.revision) != (request.facts_revision, request.document_revision):
        raise ValueError("STALE_PANEL_EDIT")
    records = {record.id: record for record in project.facts.records}
    if request.operation in {"move_technology", "move_focus"}:
        record = records.get(request.record_id)
        target = records.get(request.before_record_id) if request.before_record_id else None
        if record is None or record.kind != "technology" or request.before_record_id and (target is None
                or target.kind != "technology" or request.operation == "move_technology" and target.job_id != record.job_id):
            raise ValueError("TECHNOLOGY_MOVE_INVALID")
        if request.operation == "move_focus":
            from .technology_focus import focus_move_steps
            steps = focus_move_steps(workspace, record.id, request.before_record_id)
        else:
            steps = insert_technology(project, record, request.before_record_id, moving=True)
        return RichMutation(schemaVersion=1, projectId=workspace.project_id, clientMutationId=identity("panel"),
            actionId=request.capture.action_id, capture=request.capture, kind="panel", steps=steps) if steps else None
    if request.operation in {"add_to_focus", "remove_from_focus"}:
        steps = focus_membership_steps(workspace, request.record_id, request.operation == "add_to_focus")
        return RichMutation(schemaVersion=1, projectId=workspace.project_id, clientMutationId=identity("panel"),
            actionId=request.capture.action_id, capture=request.capture, kind="panel", steps=steps) if steps else None
    if request.operation == "clear_technologies":
        if request.job_id is not None and (request.job_id not in records or records[request.job_id].kind != "employment"):
            raise ValueError("PANEL_OWNER_INVALID")
        removed = {record.id for record in records.values() if record.kind == "technology" and record.job_id == request.job_id}
        if not removed:
            return None
        candidate = project.model_copy(deep=True)
        bind_edit_lists(candidate, request.job_id)
        for identifier in sorted(removed):
            bind_exact_technology(candidate.document, records[identifier], removed)
        steps = removal_steps(candidate, records, removed)
        steps += additional_bindings(project, steps, patch_lists(project, candidate))
        return RichMutation(schemaVersion=1, projectId=workspace.project_id, clientMutationId=identity("panel"),
            actionId=request.capture.action_id, capture=request.capture, kind="panel", steps=steps)
    if request.operation == "add":
        if request.record_kind not in FIELDS:
            raise ValueError("PANEL_KIND_INVALID")
        if request.record_kind == "candidate" and any(r.kind == "candidate" for r in records.values()):
            raise ValueError("CANDIDATE_ALREADY_EXISTS")
        if request.job_id is not None and (request.record_kind != "technology" or request.job_id not in records or records[request.job_id].kind != "employment"):
            raise ValueError("PANEL_OWNER_INVALID")
        old = None
        record = new_record(request.record_kind, request.job_id)
    else:
        old = records.get(request.record_id)
        if old is None or old.kind not in FIELDS:
            raise ValueError("PANEL_RECORD_MISSING")
        record = old.model_copy(deep=True)
    blocks = list(project.document.blocks())
    positions = placements(project.document)
    steps = []
    if request.operation == "remove":
        if record.kind == "claim" and project.facts.mode in {"digest", "imported"}:
            steps.append(RemoveRecord(kind="remove_record", recordId=record.id, beforeRevision=record.revision))
            for block in blocks:
                kept = [link for link in block.provenance if not (link.kind == "citation" and link.record_id == record.id)]
                if kept != block.provenance:
                    changed = block.model_copy(deep=True)
                    changed.provenance = kept
                    steps.append(put_block(changed, positions))
            return RichMutation(schemaVersion=1, projectId=workspace.project_id, clientMutationId=identity("panel"),
                actionId=request.capture.action_id, capture=request.capture, kind="panel", steps=steps)
        if record.kind == "technology":
            original = project
            project = project.model_copy(deep=True)
            bind_edit_lists(project, record.job_id)
            bind_exact_technology(project.document, record)
            rebound = patch_lists(original, project)
        removed = {record.id}
        if record.kind == "employment":
            removed.update(r.id for r in records.values() if getattr(r, "job_id", None) == record.id)
        steps += removal_steps(project, records, removed)
        if record.kind == "technology":
            steps += additional_bindings(project, steps, rebound)
    else:
        if request.operation in {"add_period", "remove_period"}:
            if record.kind != "employment":
                raise ValueError("PANEL_PERIOD_INVALID")
            if request.operation == "add_period":
                record.periods.append(period())
            else:
                if not any(p.id == request.period_id for p in record.periods):
                    raise ValueError("PANEL_PERIOD_MISSING")
                record.periods = [p for p in record.periods if p.id != request.period_id]
        allowed = set(FIELDS[record.kind])
        if record.kind == "employment":
            allowed.update(f"period:{p.id}:{part}" for p in record.periods for part in ("start", "end", "present"))
            if request.operation == "add":
                values = {f"period:{record.periods[0].id}:{key}": value for key, value in request.values.items() if key in {"start", "end", "present"}}
                values.update({key: value for key, value in request.values.items() if key not in {"start", "end", "present"}})
            else:
                values = request.values
        else:
            values = request.values
        if not set(values) <= allowed or any(len(value) > 16000 for value in values.values()):
            raise ValueError("PANEL_FIELD_INVALID")
        for key, value in values.items():
            set_text(record, key, value)
        record.user_corrected = True
        steps.append(PutRecord(kind="put_record", beforeRevision=old.revision if old else None, record=record))
        if old is None and record.kind == "technology":
            steps += insert_technology(project, record)
        elif old is None:
            parent = next((b for b in blocks if getattr(b.props, "record_id", None) == request.job_id), None) if request.job_id else None
            region = "main" if record.kind in {"employment", "technology"} else "header" if record.kind == "candidate" else "sidebar"
            siblings = parent.children if parent else next(r.blocks for r in project.document.regions if r.id == region)
            previous = siblings[-1].id if siblings else None
            for value in record_blocks(record):
                block = TypeAdapter(RichBlock).validate_python(value)
                target = "sidebar" if record.kind == "candidate" and value["content"][0]["fieldKey"] == "location" else parent.id if parent else region
                after = previous if target != "sidebar" or region == "sidebar" else next((r.blocks[-1].id for r in project.document.regions if r.id == "sidebar" and r.blocks), None)
                steps.append(PutBlock(kind="put_block", parentId=target, afterId=after, beforeRevision=None, block=block))
                previous = block.id
        else:
            preview = workspace.model_copy(deep=True)
            rebound = set()
            if record.kind == "technology":
                rebound = bind_edit_lists(preview.project, record.job_id)
                rebound |= bind_exact_technology(preview.project.document, old)
            preview.project.facts.records = [record if r.id == record.id else r for r in preview.project.facts.records]
            steps += linked_field_steps(preview, [record.id], tuple(values) if record.kind == "technology" else ())
            replaced = {step.block.id for step in steps if isinstance(step, PutBlock)}
            steps += [put_block(block, positions) for block in preview.project.document.blocks() if block.id in rebound - replaced]
            if record.kind == "employment":
                steps = endpoint_steps(project, record, steps, positions)
            if request.operation in {"add_period", "remove_period"}:
                steps = period_blocks(project, record, old, steps, positions)
    return RichMutation(schemaVersion=1, projectId=workspace.project_id, clientMutationId=identity("panel"),
        actionId=request.capture.action_id, capture=request.capture, kind="panel", steps=steps + focus_order_steps(workspace, steps))


def removal_steps(project, records, removed):
    blocks = list(project.document.blocks())
    positions = placements(project.document)
    steps = [RemoveRecord(kind="remove_record", recordId=id, beforeRevision=records[id].revision) for id in sorted(removed)]
    removed_blocks = set()
    def prune(block):
        if getattr(block.props, "record_id", None) in removed:
            removed_blocks.update(b.id for b in descend(block))
            return
        for child in block.children:
            prune(child)
    for region in project.document.regions:
        for block in region.blocks:
            prune(block)
    steps += [RemoveBlock(kind="remove_block", blockId=b.id, beforeRevision=b.revision) for b in blocks
        if b.id in removed_blocks and positions[b.id][0] not in removed_blocks]
    for block in blocks:
        if block.id in removed_blocks:
            continue
        copy, changed = block.model_copy(deep=True), False
        for _, content in inline_groups(copy):
            kept = [span for span in content if not isinstance(span, FactFieldSpan) or span.record_id not in removed]
            if len(kept) != len(content):
                content[:] = technology_delimiters(content, kept, records); changed = True
        if changed:
            copy.provenance = [link for link in copy.provenance if link.kind != "field_binding" or link.record_id not in removed]
            steps.append(put_block(copy, positions))
    return prune_empty_lists(project, steps)


def technology_delimiters(before, kept, records):
    parts = list_parts(before, records)
    if parts:
        retained = {span.record_id for span in kept if isinstance(span, FactFieldSpan)}
        return rebuild(parts, [entry for entry in parts[1] if entry[0].record_id in retained])
    def delimiter(span):
        return isinstance(span, StyledText) and not span.text.strip(" \t\r\n·,;|/")
    if not any(isinstance(span, FactFieldSpan) for span in before) or not all(delimiter(span) or
            isinstance(span, FactFieldSpan) and span.field_key == "display" and span.record_id in records
            and records[span.record_id].kind == "technology" for span in before):
        return remove_from_prose(before, kept, records)
    # Only technology-only list separators can collapse; authored prose stays literal.
    result = []
    for span in kept:
        if delimiter(span) and (not result or delimiter(result[-1])):
            continue
        result.append(span)
    if result and delimiter(result[-1]): result.pop()
    return result


def bind_exact_technology(document, original, removal_scope=None):
    from .models.rich_document import StyledText
    changed = set()
    for block in document.blocks():
        if not any(link.kind == "citation" and link.record_id == original.id for link in block.provenance):
            continue
        if removal_scope is not None and any(link.kind == "citation" and link.record_id not in removal_scope for link in block.provenance):
            continue
        for _, content in inline_groups(block):
            if not content or not all(isinstance(span, StyledText) for span in content) or "".join(span.text for span in content) != original.display.raw_text:
                continue
            root = identity("binding")
            content[:] = [FactFieldSpan(type="fact_field", bindingId=identity("binding"), bindingRootId=root, recordId=original.id,
                fieldKey="display", text=span.text, styles=span.styles, syncedFactRevision=original.display.revision) for span in content]
            changed.add(block.id)
    return changed


def descend(block):
    yield block
    for child in block.children:
        yield from descend(child)


def put_block(block, positions):
    return PutBlock(kind="put_block", parentId=positions[block.id][0], afterId=positions[block.id][1],
        beforeRevision=block.revision, block=block.model_copy(update={"children": []}), keepChildren=True)


def period_blocks(project, record, old, steps, positions):
    current = {p.id for p in record.periods}
    removed = {p.id for p in old.periods} - current
    added = current - {p.id for p in old.periods}
    for block in project.document.blocks():
        staged = next((step.block for step in reversed(steps) if isinstance(step, PutBlock)
                       and step.block.id == block.id), block)
        copy, changed = staged.model_copy(deep=True), False
        for _, content in inline_groups(copy):
            kept = [s for s in content if not isinstance(s, FactFieldSpan) or s.record_id != record.id
                or not any(s.field_key.startswith(f"period:{id}:") for id in removed)]
            if len(kept) != len(content):
                content[:] = kept; changed = True
        if changed:
            copy.provenance = [link for link in copy.provenance if link.kind != "field_binding" or link.record_id != record.id
                or not any(link.field_key.startswith(f"period:{id}:") for id in removed)]
            steps = [s for s in steps if not isinstance(s, PutBlock) or s.block.id != block.id]
            steps.append(put_block(copy, positions))
    owner = next((b for b in project.document.blocks() if getattr(b.props, "record_id", None) == record.id), None)
    if added:
        parent = owner.id if owner else "main"
        previous = owner.children[-1].id if owner and owner.children else None
        for p in record.periods:
            if p.id not in added:
                continue
            block = TypeAdapter(RichBlock).validate_python(period_block(record, p))
            steps.append(PutBlock(kind="put_block", parentId=parent, afterId=previous, beforeRevision=None, block=block)); previous = block.id
    return steps


def period_block(record, period):
    start = field_block(record, f"period:{period.id}:start")
    end = field_block(record, f"period:{period.id}:present" if period.present.value is True else f"period:{period.id}:end")
    start["content"] += [{"type": "text", "text": " — ", "styles": {}}, *end["content"]]
    start["provenance"] += end["provenance"]
    return start


def endpoint_steps(project, record, steps, positions):
    from .rich_fields import occurrences
    groups = occurrences(project.document)
    replacements = {step.block.id: step.block.model_copy(deep=True) for step in steps if isinstance(step, PutBlock)}
    touched = set()
    for period in record.periods:
        active = "present" if period.present.value is True else "end"
        key = f"period:{period.id}:{active}"
        if any(group.record_id == record.id and group.key == key for group in groups.values()):
            continue
        other = f"period:{period.id}:{'end' if active == 'present' else 'present'}"
        for block in project.document.blocks():
            copy = replacements.get(block.id, block.model_copy(deep=True))
            for _, content in inline_groups(copy):
                spans = [span for span in content if isinstance(span, FactFieldSpan) and span.record_id == record.id and span.field_key == other]
                if not spans:
                    continue
                text = getattr(period, active).raw_text
                for index, span in enumerate(spans):
                    part = text if index == len(spans) - 1 else text[:len(span.text)]
                    text = text[len(part):]
                    span.field_key, span.text = key, part
                for link in copy.provenance:
                    if link.kind == "field_binding" and link.record_id == record.id and link.field_key == other:
                        link.field_key = key
                replacements[block.id] = copy; touched.add(block.id)
    return [step for step in steps if not isinstance(step, PutBlock) or step.block.id not in touched] + [put_block(replacements[id], positions) for id in sorted(touched)]


def narrative_steps(workspace, blocks, proposal):
    from .models.rich_document import StyledText, Hyperlink
    allowed = {block.id: block for block in blocks}
    positions, copies, touched = placements(workspace.project.document), {}, set()
    if not set(proposal.uncertain) <= allowed.keys():
        raise ValueError("PANEL_NARRATIVE_SCOPE_INVALID")
    for update in proposal.updates:
        pair = (update.block_id, update.cell_id)
        if update.block_id not in allowed or pair in touched or update.block_id in proposal.uncertain:
            raise ValueError("PANEL_NARRATIVE_SCOPE_INVALID")
        touched.add(pair)
        block = copies.setdefault(update.block_id, allowed[update.block_id].model_copy(deep=True))
        if block.type == "code":
            if update.cell_id is not None:
                raise ValueError("PANEL_NARRATIVE_SCOPE_INVALID")
            block.content = update.text
            continue
        container = update.cell_id if block.type == "table" else "caption" if block.type == "image" else "content"
        content = next((content for key, content in inline_groups(block) if key == container), None)
        if content is None or (block.type != "table" and update.cell_id is not None) or any(isinstance(s, FactFieldSpan) for s in content):
            raise ValueError("PANEL_NARRATIVE_SCOPE_INVALID")
        runs = [part for span in content for part in (span.content if isinstance(span, Hyperlink) else [span])]
        if not runs:
            content.append(StyledText(type="text", text=update.text, styles={}))
        else:
            rest = update.text
            for index, run in enumerate(runs):
                value = rest if index == len(runs) - 1 else rest[:len(run.text)]
                rest = rest[len(value):]
                run.text = value
    return [put_block(copy, positions) for copy in copies.values()]


def has_exact_fields(block):
    return any(isinstance(span, FactFieldSpan) for _, content in inline_groups(block) for span in content)
