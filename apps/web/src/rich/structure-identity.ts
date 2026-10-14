import { Extension } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";

function value(node: PMNode, key: string): string | null {
  const candidate: unknown = node.attrs[key]; return typeof candidate === "string" && candidate ? candidate : null;
}
export function sourceIds(node: PMNode): string[] {
  const raw = value(node, "foldcvSources");
  if (!raw) return [];
  let ids: unknown;
  try { ids = JSON.parse(raw); } catch { return []; }
  if (!Array.isArray(ids) || !ids.every((id: unknown) => typeof id === "string")) return [];
  return ids;
}
export const structureIdentityAttributes = Extension.create({ name: "foldcv-structural-identity", addGlobalAttributes: () => [{
  types: ["blockContainer"], attributes: { foldcvSources: { default: null,
    parseHTML: (element: HTMLElement) => element.getAttribute("data-foldcv-sources"),
    renderHTML: (attrs: Record<string, unknown>) => typeof attrs["foldcvSources"] === "string" ? { "data-foldcv-sources": attrs["foldcvSources"] } : {} } },
}] });

/** Copies cite their source; the mapped original remains the sole primary owner. */
export function structureIdentityPlugin() {
  return new Plugin({ key: new PluginKey("foldcv-structural-identity"), appendTransaction: (transactions, before, after) => {
    const blocks = new Map<string, number>();
    const owners = new Map<string, number[]>();
    after.doc.descendants((node, pos) => {
      if (node.type.name === "blockContainer") { const id = value(node, "id"); if (id) blocks.set(id, pos); }
      if (node.type.name === "section") { const id = value(node, "recordId"); if (id) owners.set(id, [...(owners.get(id) ?? []), pos]); }
    });
    const originalOwners = new Map<string, number>();
    const merged = new Map<string, Set<string>>();
    before.doc.descendants((node, pos) => {
      if (node.type.name === "section") {
        const record = value(node, "recordId"); if (!record) return;
        let mapped = pos; for (const tr of transactions) mapped = tr.mapping.map(mapped, 1);
        originalOwners.set(record, mapped);
      }
      if (node.type.name !== "blockContainer" || node.firstChild?.type.name === "region") return;
      const id = value(node, "id"); if (!id || blocks.has(id)) return;
      // A merge carries surviving text from the old end into its destination.
      let mapped = pos + node.nodeSize - 2, deleted = false;
      for (const tr of transactions) { const result = tr.mapping.mapResult(mapped, -1); mapped = result.pos; deleted ||= result.deletedAcross; }
      if (deleted || mapped > after.doc.content.size) return;
      const resolved = after.doc.resolve(mapped);
      for (let depth = resolved.depth; depth > 0; depth--) {
        const target = resolved.node(depth), targetId = value(target, "id");
        if (target.type.name !== "blockContainer" || !targetId || target.firstChild?.type.name === "region") continue;
        const sources = merged.get(targetId) ?? new Set<string>();
        for (const source of [...sourceIds(node), id]) sources.add(source);
        merged.set(targetId, sources); break;
      }
    });
    const tr = after.tr;
    after.doc.descendants((node, pos) => {
      if (node.type.name === "blockContainer") {
        const id = value(node, "id"), old = sourceIds(node), added = id ? merged.get(id) : undefined;
        const ids = [...new Set([...old, ...(id && !old.length ? [id] : []), ...(added ?? [])])];
        if (ids.length && JSON.stringify(ids) !== value(node, "foldcvSources")) tr.setNodeMarkup(pos, undefined, { ...node.attrs, foldcvSources: JSON.stringify(ids) });
      }
      if (node.type.name === "section") {
        const record = value(node, "recordId"), positions = record ? owners.get(record) ?? [] : [];
        const original = record ? originalOwners.get(record) : undefined;
        const keep = original !== undefined && positions.includes(original) ? original : positions[0];
        if (positions.length > 1 && pos !== keep) tr.setNodeMarkup(pos, undefined, { ...node.attrs, recordId: "" });
      }
    });
    return tr.docChanged ? tr : null;
  } });
}

export function readBlockSources(doc: PMNode): Map<string, string[]> {
  const result = new Map<string, string[]>();
  doc.descendants(node => { const id = value(node, "id"); if (node.type.name === "blockContainer" && id) result.set(id, sourceIds(node)); });
  return result;
}
