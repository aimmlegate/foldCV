"""Atomic bounded tree/fact patches; persistence acknowledgments do not edit content."""

import hashlib

from .models.rich_document import FactFieldSpan, Hyperlink, ImageBlock, TableBlock
from .models.rich_mutations import MoveBlock, PutBlock, PutRecord, RemoveBlock, RemoveRecord, ReplaceInlineRange
from .models.rich_workspace import RichMutationReplay, WorkspaceV6
from .rich_fact_mutations import apply_record_mutations


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
    return "".join(child.text for child in span.content) if isinstance(span, Hyperlink) else span.text


def utf16_slice(text, start, end):
    try:
        return text.encode("utf-16-le")[start * 2:end * 2].decode("utf-16-le")
    except UnicodeError:
        raise RichMutationFailure("RICH_RANGE_INVALID") from None


def cut_inline(content, start, end):
    result, cursor = [], 0
    for span in content:
        length = len(inline_text(span).encode("utf-16-le")) // 2
        lo, hi = max(0, start - cursor), min(length, end - cursor)
        if hi > lo:
            kept = span.model_copy(deep=True)
            if isinstance(kept, Hyperlink):
                kept.content = cut_inline(kept.content, lo, hi)
            else:
                kept.text = utf16_slice(kept.text, lo, hi)
                if isinstance(kept, FactFieldSpan) and (lo != 0 or hi != length):
                    # A partial field selection is authored text, not another exact binding.
                    from .models.rich_document import StyledText
                    kept = StyledText(type="text", text=kept.text, styles=kept.styles)
            result.append(kept)
        cursor += length
    return result


def apply_rich_mutation(workspace: WorkspaceV6, request):
    if request.project_id != workspace.project_id or workspace.project is None:
        raise RichMutationFailure("RICH_PROJECT_MISMATCH")
    checksum = hashlib.sha256(request.model_dump_json(by_alias=True).encode()).hexdigest()
    replay = next((item for item in workspace.mutation_replay if item.client_mutation_id == request.client_mutation_id), None)
    if replay:
        if replay.request_sha256 != checksum:
            raise RichMutationFailure("MUTATION_ID_REUSED")
        return workspace.model_copy(deep=True), True
    result = workspace.model_copy(deep=True)
    project, document = result.project, result.project.document
    facts = {record.id: record for record in project.facts.records}
    blocks = {block.id: block for block in document.blocks()}
    for step in request.steps:
        if isinstance(step, (PutRecord, RemoveRecord)):
            continue
        identifier = step.block.id if isinstance(step, PutBlock) else step.block_id
        original = blocks.get(identifier)
        if step.before_revision != (original.revision if original else None):
            raise RichMutationFailure("STALE_MUTATION")
    for stamp in request.capture.dependencies:
        target = blocks.get(stamp.id) if stamp.kind == "block" else facts.get(stamp.id) if stamp.kind == "record" else None
        if stamp.kind in {"block", "record"} and (target is None or target.revision != stamp.revision):
            raise RichMutationFailure("STALE_MUTATION")
    record_steps = [step for step in request.steps if isinstance(step, (PutRecord, RemoveRecord))]
    try:
        project.facts = apply_record_mutations(project.facts, record_steps, request.action_id).facts
    except ValueError:
        raise RichMutationFailure("STALE_MUTATION") from None
    for step in request.steps:
        if isinstance(step, (PutRecord, RemoveRecord)):
            continue
        identifier = step.block.id if isinstance(step, PutBlock) else step.block_id
        found = locate(document, identifier)
        old = found[0][found[1]] if found else None
        if isinstance(step, (PutBlock, MoveBlock)):
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
            setattr(target, key, cut_inline(content, 0, step.start) + step.content + cut_inline(content, step.end, length))
            if hasattr(target, "revision"):
                target.revision = max(target.revision, document.revision) + 1
            old.revision = max(old.revision, document.revision) + 1
    result.project_revision += 1
    result.document_revision += 1
    project.revision, document.revision = result.project_revision, result.document_revision
    result.mutation_replay.append(RichMutationReplay(clientMutationId=request.client_mutation_id,
        requestSha256=checksum, resultingRevision=result.project_revision))
    return WorkspaceV6.model_validate(result.model_dump(by_alias=True)), False


def subtree(block):
    yield block
    for child in block.children:
        yield from subtree(child)
