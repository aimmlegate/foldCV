import type { Transaction } from "@tiptap/pm/state";

export function projectRegionChildren<Block>(transaction: Transaction,
  regions: readonly { id: string; children: Block[] }[], update: (id: string, children: Block[]) => void): void {
  const targets = new Map(regions.map(region => [region.id, region]));
  if (targets.size !== regions.length) throw new Error("Duplicate region projection");
  const found = new Set<string>();
  const groups: { from: number; to: number }[] = [];
  transaction.doc.descendants((node, position) => {
    const id: unknown = node.attrs["id"];
    if (node.type.name !== "blockContainer" || typeof id !== "string" || !targets.has(id)) return;
    const marker = node.firstChild;
    if (marker?.type.name !== "region") throw new Error("Projection target is not a region");
    found.add(id);
    const group = node.lastChild;
    if (!targets.get(id)?.children.length && group?.type.name === "blockGroup") {
      const from = position + 1 + marker.nodeSize;
      groups.push({ from, to: from + group.nodeSize });
    }
    return false;
  });
  if (found.size !== targets.size) throw new Error("Projection region is missing");
  // BlockNote treats children: [] as no update; canonical empty regions need removal.
  for (const group of groups.reverse()) transaction.delete(group.from, group.to);
  for (const region of regions) if (region.children.length) update(region.id, region.children);
}
