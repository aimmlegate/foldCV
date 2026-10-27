import type { Transaction } from "@tiptap/pm/state";

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
