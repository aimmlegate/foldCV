import type { RichDocumentV1, Content } from "../contracts/generated/rich_document_v1";
import type { RichBlock } from "./save-queue";

export function copyBlock(block: RichBlock, allocate: () => string = () => crypto.randomUUID(), roots = new Map<string, string>()): RichBlock {
  const inline = (content: Content): Content => content.map(span => {
    if (span.type !== "fact_field") return structuredClone(span);
    const bindingId = allocate(), oldRoot = span.bindingRootId ?? span.bindingId;
    const bindingRootId = roots.get(oldRoot) ?? bindingId; roots.set(oldRoot, bindingRootId);
    return { ...span, bindingId, bindingRootId };
  });
  const base = { ...structuredClone(block), id: allocate(), revision: 1, children: block.children.map(child => copyBlock(child, allocate, roots)),
    provenance: block.provenance.filter(link => link.kind !== "working_owner").map(link => ({ ...structuredClone(link), id: allocate() })) };
  if (base.type === "section") return { ...base, props: { ...base.props, recordId: null }, content: inline(base.content) };
  if (base.type === "table") {
    const rows = base.content.rows.map(row => ({ ...row, id: allocate(),
      cells: row.cells.map(cell => ({ ...cell, id: allocate(), revision: 1, content: inline(cell.content) })) }));
    const first = rows[0]; if (!first) throw new Error("RICH_TABLE_EMPTY");
    return { ...base, content: { ...base.content, rows: [first, ...rows.slice(1)] } };
  }
  if (base.type === "image") return { ...base, props: { ...base.props, caption: inline(base.props.caption) } };
  if (base.type === "code" || base.type === "divider") return base;
  return { ...base, content: inline(base.content) };
}
export function moveBlock(document: RichDocumentV1, id: string, parent: string): RichDocumentV1 {
  const next = structuredClone(document);
  let block: RichBlock | undefined;
  function remove(blocks: RichBlock[]): boolean {
    for (const [index, current] of blocks.entries()) {
      if (current.id === id) { block = current; blocks.splice(index, 1); return true; }
      if (remove(current.children)) return true;
    } return false;
  }
  for (const region of next.regions) if (remove(region.blocks)) break;
  if (!block) throw new Error("RICH_BLOCK_MISSING");
  function find(blocks: RichBlock[]): RichBlock | undefined {
    for (const current of blocks) { if (current.id === parent) return current; const found = find(current.children); if (found) return found; } return undefined;
  }
  const region = next.regions.find(region => region.id === parent), owner = next.regions.flatMap(region => region.blocks).map(block => find([block])).find(block => block !== undefined);
  if (region) region.blocks.push(block);
  else if (owner) owner.children.push(block);
  else throw new Error("RICH_MOVE_TARGET_INVALID");
  return next;
}

export function mergeBlocks(document: RichDocumentV1, destination: string, source: string): RichDocumentV1 {
  const next = structuredClone(document);
  const entries = new Map<string, { block: RichBlock; siblings: RichBlock[] }>();
  const visit = (blocks: RichBlock[]) => { for (const block of blocks) { entries.set(block.id, { block, siblings: blocks }); visit(block.children); } };
  next.regions.forEach(region => visit(region.blocks));
  const target = entries.get(destination), removed = entries.get(source);
  if (!target || !removed || target === removed || !Array.isArray(target.block.content) || !Array.isArray(removed.block.content)
    || target.block.type === "section" || removed.block.type === "section") throw new Error("Выберите два соседних текстовых блока");
  let ancestor = removed.block.children;
  while (ancestor.length) { if (ancestor.some(block => block.id === destination)) throw new Error("Нельзя объединить блок с его потомком"); ancestor = ancestor.flatMap(block => block.children); }
  target.block.content = [...target.block.content, ...removed.block.content];
  target.block.children.push(...removed.block.children);
  const links = new Map(target.block.provenance.map(link => [link.id, link]));
  for (const link of removed.block.provenance) {
    if (!links.has(link.id)) links.set(link.id, link);
    else if (JSON.stringify(links.get(link.id)) !== JSON.stringify(link)) { const id = crypto.randomUUID(); links.set(id, { ...link, id }); }
  }
  target.block.provenance = [...links.values()];
  removed.siblings.splice(removed.siblings.indexOf(removed.block), 1);
  return next;
}
