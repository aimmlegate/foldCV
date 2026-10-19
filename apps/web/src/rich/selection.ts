import type { Transaction } from "@tiptap/pm/state";
import type { Node } from "@tiptap/pm/model";
import type { RichSelection } from "../contracts/generated/rich_selection";

export function singleRewriteRange(selection: ReturnType<typeof selectedRange>): boolean {
  return !!selection && selection.kind !== "blocks" && selection.blockIds.length === 1
    && selection.anchor.blockId === selection.head.blockId && selection.blockIds[0] === selection.anchor.blockId
    && selection.anchor.cellId === selection.head.cellId && selection.anchor.offset < selection.head.offset;
}

function textOffset(node: Node, position: number): number {
  return node.textBetween(0, Math.max(0, Math.min(node.content.size, position)), "",
    leaf => leaf.type.name === "hardBreak" ? "\n" : "").length;
}

export function selectionLocation(tr: Transaction): string | null {
  const position = tr.selection.$head;
  let cell: string | null = null;
  for (let depth = position.depth; depth > 0; depth--) {
    const node = position.node(depth), id: unknown = node.attrs["id"], cellId: unknown = node.attrs["foldcvNodeId"];
    if ((node.type.name === "tableCell" || node.type.name === "tableHeader") && typeof cellId === "string") cell = cellId;
    if (node.type.name === "blockContainer" && typeof id === "string") return JSON.stringify([id, cell]);
  }
  return null;
}

/** Public ProseMirror positions are converted to offsets inside FoldCV's stable nodes. */
export function selectedRange(tr: Transaction): Omit<RichSelection, "capture" | "textSha256"> | null {
  if (tr.selection.empty) return null;
  const parts: { id: string; start: number; end: number; cellId: string | null }[] = [];
  tr.doc.descendants((node, pos) => {
    if (node.type.name !== "blockContainer" || !node.firstChild || node.firstChild.type.name === "region") return;
    const id: unknown = node.attrs["id"];
    if (typeof id !== "string") return;
    const start = pos + 2, end = start + node.firstChild.content.size;
    if (node.firstChild.type.name === "table") {
      node.firstChild.descendants((cell, offset) => {
        if (cell.type.name !== "tableCell" && cell.type.name !== "tableHeader") return;
        const cellId: unknown = cell.attrs["foldcvNodeId"];
        const a = start + offset + 2, b = a + (cell.firstChild?.content.size ?? 0);
        if (typeof cellId === "string" && cell.firstChild && tr.selection.from < b && tr.selection.to > a)
          parts.push({ id, cellId, start: textOffset(cell.firstChild, tr.selection.from - a), end: textOffset(cell.firstChild, tr.selection.to - a) });
      });
    } else if (tr.selection.from < end && tr.selection.to > start) {
      const offset = (position: number) => textOffset(node.firstChild!, position - start);
      parts.push({ id, cellId: null, start: offset(tr.selection.from), end: offset(tr.selection.to) });
    }
  });
  const first = parts[0], last = parts.at(-1);
  if (!first || !last) return null;
  return { kind: first.cellId ? "table_cells" : "text", anchor: { blockId: first.id, cellId: first.cellId, offset: first.start },
    head: { blockId: last.id, cellId: last.cellId, offset: last.end }, blockIds: [first.id, ...[...new Set(parts.map(part => part.id))].filter(id => id !== first.id)] };
}
