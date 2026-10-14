import type { Transaction } from "@tiptap/pm/state";
import type { RichSelection } from "../contracts/generated/rich_selection";

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
        if (typeof cellId === "string" && tr.selection.from < b && tr.selection.to > a)
          parts.push({ id, cellId, start: Math.max(0, tr.selection.from - a), end: Math.min(b - a, tr.selection.to - a) });
      });
    } else if (tr.selection.from < end && tr.selection.to > start) {
      // textBetween counts the text of custom field nodes rather than their wrapper tokens.
      const offset = (position: number) => node.firstChild?.textBetween(0, Math.max(0, Math.min(end - start, position - start)), "", "") .length ?? 0;
      parts.push({ id, cellId: null, start: offset(tr.selection.from), end: offset(tr.selection.to) });
    }
  });
  const first = parts[0], last = parts.at(-1);
  if (!first || !last) return null;
  return { kind: first.cellId ? "table_cells" : "text", anchor: { blockId: first.id, cellId: first.cellId, offset: first.start },
    head: { blockId: last.id, cellId: last.cellId, offset: last.end }, blockIds: [first.id, ...[...new Set(parts.map(part => part.id))].filter(id => id !== first.id)] };
}
