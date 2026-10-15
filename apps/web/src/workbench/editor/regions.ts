import type { Transaction } from "@tiptap/pm/state";

// BlockNote inserts a placeholder when replacing existing children with [].
export function restoreEmptyRegions(transaction: Transaction, empty: ReadonlySet<string>): void {
  const groups: { from: number; to: number }[] = [];
  transaction.doc.descendants((node, position) => {
    const id: unknown = node.attrs["id"];
    if (node.type.name !== "blockContainer" || typeof id !== "string" || !empty.has(id) || node.firstChild?.type.name !== "region") return;
    const group = node.lastChild;
    if (group?.type.name !== "blockGroup") return false;
    const placeholder = group.firstChild;
    if (group.childCount !== 1 || placeholder?.childCount !== 1 || placeholder.firstChild?.type.name !== "paragraph" || placeholder.firstChild.content.size !== 0)
      throw new Error("Empty region projection contains authored content");
    const from = position + 1 + node.firstChild.nodeSize;
    groups.push({ from, to: from + group.nodeSize });
    return false;
  });
  for (const group of groups.reverse()) transaction.delete(group.from, group.to);
}
