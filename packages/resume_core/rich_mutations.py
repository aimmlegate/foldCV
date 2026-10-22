"""Atomic bounded tree/fact patches; persistence acknowledgments do not edit content."""

import hashlib
import uuid

from .models.rich_document import FactFieldSpan, Hyperlink, ImageBlock, TableBlock
from .models.template_document import BoundLink, ManualScopeSpan
from .models.rich_mutations import MoveBlock, PutBlock, PutRecord, RemoveBlock, RemoveRecord, ReplaceInlineRange
from .models.rich_workspace import RichMutationReplay, WorkspaceV6
from .rich_fact_mutations import apply_record_mutations
from .rich_dependencies import dependencies_current
from .rich_fields import synchronize_binding_revisions
from .models.template_mutations import RestoreAuthoredBlockPatch, TemplateMutationV1
from .template_mutations import DOMAIN_STEPS, apply_fact_steps, apply_issue_steps, check_history, check_tree_targets
from .template_preparation_ids import allocate_id


class RichMutationFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def locate(document, identifier):
    def visit(items, parent):
        for index, block in enumerate(items):
            if block.id == identifier:
                return items, index, parent
            found = visit(block.children, block)
            if found:
                return found
        return None
    for region in document.regions:
        found = visit(region.blocks, region)
        if found:
            return found
    return None


def parent_items(document, identifier):
    for region in document.regions:
        if region.id == identifier:
            return region.blocks, region
    found = locate(document, identifier)
    if found:
        return found[0][found[1]].children, found[0][found[1]]
    raise RichMutationFailure("RICH_PARENT_MISSING")


def inline_text(span):
    return "".join(child.text for child in span.content) if isinstance(span, (Hyperlink,BoundLink)) else span.text


def utf16_slice(text, start, end):
    try:
        return text.encode("utf-16-le")[start * 2:end * 2].decode("utf-16-le")
    except UnicodeError:
        raise RichMutationFailure("RICH_RANGE_INVALID") from None


def cut_inline(content, start, end, *, id_factory=None, allocation_path=(), empty_end=False, _origin=0):
    result, cursor = [], _origin
    for index, span in enumerate(content):
        length = len(inline_text(span).encode("utf-16-le")) // 2
        lo, hi = max(0, start - cursor), min(length, end - cursor)
        empty_selected = start <= cursor < end or empty_end and cursor == end
        if isinstance(span, (Hyperlink, BoundLink)):
            kept = span.model_copy(deep=True)
            kept.content = cut_inline(kept.content, start, end, id_factory=id_factory,
                allocation_path=(*allocation_path, index, 'content'), empty_end=empty_end, _origin=cursor)
            if kept.content or length == 0 and empty_selected:
                result.append(kept)
        elif hi > lo or length == 0 and empty_selected:
            kept = span.model_copy(deep=True)
            kept.text = utf16_slice(kept.text, lo, hi) if length else ''
            if isinstance(kept, FactFieldSpan) and (lo != 0 or hi != length):
                kept.binding_root_id = kept.binding_root_id or kept.binding_id
                kept.binding_id = allocate_id(id_factory, 'binding',
                    ['fragment', span.binding_id, lo, hi, list(allocation_path), index]) if id_factory is not None else (
                        "binding-" + uuid.uuid4().hex)
            elif isinstance(kept, ManualScopeSpan) and (lo != 0 or hi != length):
                if id_factory is None:
                    raise RichMutationFailure('RICH_RANGE_INVALID')
                kept.fragment_id = allocate_id(id_factory, 'manual-fragment',
                    ['fragment', span.fragment_id, lo, hi, list(allocation_path), index])
            result.append(kept)
        cursor += length
    return result


def mutation_sha256(request):
    return hashlib.sha256(request.model_dump_json(by_alias=True).encode()).hexdigest()


def apply_rich_mutation(workspace: WorkspaceV6, request, *, history_authorization=None):
    if request.project_id != workspace.project_id or workspace.project is None:
        raise RichMutationFailure("RICH_PROJECT_MISMATCH")
    checksum = mutation_sha256(request)
    replay = next((item for item in workspace.mutation_replay if item.client_mutation_id == request.client_mutation_id), None)
    if replay:
        if replay.request_sha256 != checksum:
            raise RichMutationFailure("MUTATION_ID_REUSED")
        return workspace.model_copy(deep=True), True
    template = workspace.schema_version == 7
    replay_authorized = False
    if template and not isinstance(request, TemplateMutationV1):
        raise RichMutationFailure('RICH_PATCH_INVALID')
    if template:
        try:
            check_tree_targets(request.steps)
            from .template_ranges import validate_flank_ids
            validate_flank_ids(workspace, request)
            from .template_scope_displays import guard_scope_displays
            guard_scope_displays(workspace.project, request)
        except ValueError:
            raise RichMutationFailure('RICH_PATCH_INVALID') from None
    if isinstance(request, TemplateMutationV1):
        if not template:
            raise RichMutationFailure('RICH_PROJECT_MISMATCH')
        try:
            replay_authorized = check_history(workspace, request, history_authorization)
        except ValueError:
            raise RichMutationFailure('STALE_MUTATION') from None
    result = workspace.model_copy(deep=True)
    project, document = result.project, result.project.document
    facts = {record.id: record for record in project.facts.records}
    blocks = {block.id: block for block in document.blocks()}
    for step in request.steps:
        if isinstance(step, DOMAIN_STEPS):
            continue
        identifier = step.block.id if isinstance(step, PutBlock) else step.block_id
        original = blocks.get(identifier)
        if step.before_revision != (original.revision if original else None):
            raise RichMutationFailure("STALE_MUTATION")
    if not dependencies_current(workspace, request.capture.dependencies):
        raise RichMutationFailure("STALE_MUTATION")
    record_steps = [step for step in request.steps if isinstance(step, (PutRecord, RemoveRecord))]
    try:
        project.facts = apply_fact_steps(project.facts, request, replay_authorized) if template else (
            apply_record_mutations(project.facts, record_steps, request.action_id).facts)
    except ValueError:
        raise RichMutationFailure("STALE_MUTATION") from None
    for step in request.steps:
        if isinstance(step, DOMAIN_STEPS):
            continue
        identifier = step.block.id if isinstance(step, PutBlock) else step.block_id
        found = locate(document, identifier)
        old = found[0][found[1]] if found else None
        if isinstance(step, RestoreAuthoredBlockPatch):
            if old is None or not replay_authorized:
                raise RichMutationFailure('STALE_MUTATION')
            from pydantic import TypeAdapter
            from .models.template_document import TemplateBlock
            from .template_block_patches import restore_payload
            try:
                payload = restore_payload(old, step.before_semantic_hash, step.after_semantic_hash, step.patch)
                block = TypeAdapter(TemplateBlock).validate_python({**payload, 'revision': old.revision, 'children': old.children})
            except ValueError:
                raise RichMutationFailure('STALE_MUTATION') from None
            block.revision = max(document.revision, old.revision) + 1
            update_cell_revisions(block, old, document.revision)
            found[0][found[1]] = block
            found[2].revision += 1
        elif isinstance(step, (PutBlock, MoveBlock)):
            items, parent = parent_items(document, step.parent_id)
            if isinstance(step, MoveBlock) and (old is None or parent.id in {block.id for block in subtree(old)}):
                raise RichMutationFailure("RICH_MOVE_INVALID")
            if isinstance(step, PutBlock) and old is not None and found[2].id != parent.id:
                raise RichMutationFailure("RICH_MOVE_REQUIRED")
            if isinstance(step, PutBlock) and step.keep_children:
                if old is None or step.block.children:
                    raise RichMutationFailure("RICH_PATCH_INVALID")
                block = step.block.model_copy(deep=True)
                block.children = old.children
                block.revision = max(document.revision, old.revision) + 1
                update_cell_revisions(block, old, document.revision)
                found[0][found[1]] = block
                parent.revision += 1
                continue
            if found:
                found[0].pop(found[1])
                found[2].revision += 1
            positions = {block.id: index for index, block in enumerate(items)}
            if step.after_id is not None and step.after_id not in positions:
                raise RichMutationFailure("RICH_PARENT_MISSING")
            block = step.block.model_copy(deep=True) if isinstance(step, PutBlock) else old
            block.revision = max(document.revision, getattr(old, "revision", 0)) + 1
            update_cell_revisions(block, old, document.revision)
            items.insert(positions[step.after_id] + 1 if step.after_id else 0, block)
            parent.revision += 1
        elif isinstance(step, RemoveBlock):
            if found is None:
                raise RichMutationFailure("STALE_MUTATION")
            found[0].pop(found[1]); found[2].revision += 1
        elif isinstance(step, ReplaceInlineRange):
            if old is None:
                raise RichMutationFailure("STALE_MUTATION")
            target = old
            key = "content"
            if step.cell_id is not None:
                if not isinstance(old, TableBlock):
                    raise RichMutationFailure("RICH_RANGE_INVALID")
                target = next((cell for row in old.content.rows for cell in row.cells if cell.id == step.cell_id), None)
            elif step.field == "caption":
                if not isinstance(old, ImageBlock):
                    raise RichMutationFailure("RICH_RANGE_INVALID")
                target, key = old.props, "caption"
            content = getattr(target, key, None)
            if not isinstance(content, list):
                raise RichMutationFailure("RICH_RANGE_INVALID")
            length = sum(len(inline_text(span).encode("utf-16-le")) // 2 for span in content)
            if step.end > length:
                raise RichMutationFailure("RICH_RANGE_INVALID")
            if template and step.flank_bindings is not None:
                from .template_ranges import FlankResolver, splice_inline
                try:
                    resolver = FlankResolver(step.flank_bindings)
                    changed = splice_inline(content, step.start, step.end, step.content, resolver)
                    resolver.finish()
                except ValueError:
                    raise RichMutationFailure('RICH_RANGE_INVALID') from None
            else:
                changed = cut_inline(content, 0, step.start) + step.content + cut_inline(content, step.end, length, empty_end=True)
            setattr(target, key, changed)
            if hasattr(target, "revision"):
                target.revision = max(target.revision, document.revision) + 1
            old.revision = max(old.revision, document.revision) + 1
    if template:
        from .template_scope_displays import apply_scope_displays, guard_retained_scope_ownership
        try:
            apply_scope_displays(project, request, replay=replay_authorized)
            guard_retained_scope_ownership(workspace.project, project, request, replay=replay_authorized)
        except ValueError:
            raise RichMutationFailure('STALE_MUTATION') from None
    result.project_revision += 1
    result.document_revision += 1
    project.revision, document.revision = result.project_revision, result.document_revision
    synchronize_binding_revisions(project)
    if isinstance(request, TemplateMutationV1):
        try:
            from .template_anchors import apply_anchor_steps
            apply_anchor_steps(project, request, workspace.project)
            apply_issue_steps(project, request, replay_authorized, before=workspace.project)
            from .template_synchronization import apply_sync_steps
            apply_sync_steps(workspace, result, request, replay=replay_authorized)
        except ValueError:
            raise RichMutationFailure('STALE_MUTATION') from None
    result.mutation_replay.append(RichMutationReplay(clientMutationId=request.client_mutation_id,
        requestSha256=checksum, resultingRevision=result.project_revision))
    try:
        return type(workspace).model_validate(result.model_dump(by_alias=True)), False
    except ValueError:
        if not template:
            raise
        raise RichMutationFailure('RICH_PATCH_INVALID') from None


def subtree(block):
    yield block
    for child in block.children:
        yield from subtree(child)


def update_cell_revisions(block, old, document_revision):
    if not isinstance(block, TableBlock):
        return
    previous = {cell.id: cell for row in old.content.rows for cell in row.cells} if isinstance(old, TableBlock) else {}
    for row in block.content.rows:
        for cell in row.cells:
            before = previous.get(cell.id)
            if before is None:
                cell.revision = max(document_revision, cell.revision) + 1
            else:
                value = cell.model_dump(exclude={"revision"})
                cell.revision = before.revision if value == before.model_dump(exclude={"revision"}) else max(document_revision, before.revision) + 1
