import type { Content, RichDocumentV1 } from "../contracts/generated/rich_document_v1";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import { semantic } from "./fact-cells";
import { stableJson } from "./json";
import { normalizedBlock } from "./normalize";

type Block = RichDocumentV1["regions"][number]["blocks"][number];
type Step = RichMutation["steps"][number];
const equal = (left: unknown, right: unknown): boolean => stableJson(semantic(left)) === stableJson(semantic(right));

function metadata(block: Block): unknown {
  return { type: block.type, provenance: block.provenance,
    props: block.type === "image" ? { ...block.props, caption: [] } : block.props,
    content: block.type === "table" ? { ...block.content, rows: block.content.rows.map(row => ({ ...row,
      cells: row.cells.map(cell => ({ ...cell, content: [] })) })) } : null };
}

function inlineStep(block: Block, before: Content, after: Content, cellId: string | null = null,
  field: "content" | "caption" = "content"): Step[] {
  if (equal(before, after)) return [];
  const end = before.reduce((length, span) => length + (span.type === "link"
    ? span.content.reduce((sum, child) => sum + child.text.length, 0) : span.text.length), 0);
  return [{ kind: "replace_inline_range", blockId: block.id, cellId, field, start: 0, end,
    beforeRevision: block.revision, content: after }];
}

/** Keep large source citations on the server when only inline content changes. */
export function compactMutation(request: RichMutation, document: RichDocumentV1): RichMutation {
  const blocks = new Map<string, Block>();
  const visit = (items: Block[]) => { for (const block of items) { blocks.set(block.id, block); visit(block.children); } };
  document.regions.forEach(region => visit(region.blocks));
  const steps = request.steps.flatMap((step): Step[] => {
    if (step.kind !== "put_block" || !step.keepChildren || step.block.children.length) return [step];
    const previous = blocks.get(step.block.id);
    if (!previous || previous.revision !== step.beforeRevision) return [step];
    const before = normalizedBlock(previous), after = normalizedBlock(step.block);
    if (!equal(metadata(before), metadata(after))) return [step];
    if (Array.isArray(before.content) && Array.isArray(after.content)) return inlineStep(before, before.content, after.content);
    if (before.type === "image" && after.type === "image") return inlineStep(before, before.props.caption, after.props.caption, null, "caption");
    if (before.type === "table" && after.type === "table") {
      const cells = new Map(after.content.rows.flatMap(row => row.cells.map(cell => [cell.id, cell])));
      return before.content.rows.flatMap(row => row.cells.flatMap(cell => {
        const current = cells.get(cell.id);
        return current ? inlineStep(before, cell.content, current.content, cell.id) : [];
      }));
    }
    return [step];
  });
  const [first, ...rest] = steps;
  return first ? { ...request, steps: [first, ...rest] } : request;
}
