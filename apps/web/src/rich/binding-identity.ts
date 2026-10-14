import type { Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";

function binding(node: PMNode): string | null {
  const value: unknown = node.attrs["bindingId"];
  return node.type.name === "factField" && typeof value === "string" && value.length ? value : null;
}
export function bindingIdentityPlugin(allocate: () => string = () => crypto.randomUUID()) {
  return new Plugin({ key: new PluginKey("foldcv-field-bindings"), appendTransaction: (transactions, before, after) => {
    const positions = new Map<string, number[]>(), originals = new Map<string, number>();
    const originalText = new Map<string, string>(), currentText = new Map<string, string>();
    after.doc.descendants((node, pos) => { const id = binding(node); if (id) { positions.set(id, [...(positions.get(id) ?? []), pos]); currentText.set(id, (currentText.get(id) ?? "") + node.textContent); } });
    before.doc.descendants((node, pos) => {
      const id = binding(node);
      if (id) { let mapped = pos; for (const transaction of transactions) mapped = transaction.mapping.map(mapped, 1); originals.set(id, mapped); originalText.set(id, node.textContent); }
    });
    const tr = after.tr.setMeta("foldcv.binding.identities", true);
    after.doc.descendants((node, pos) => {
      if (node.type.name !== "factField") return;
      const id = binding(node), candidates = id ? positions.get(id) ?? [] : [];
      const original = id ? originals.get(id) : undefined;
      const keep = original !== undefined && candidates.includes(original) ? original : candidates[0];
      if (!id || (candidates.length > 1 && pos !== keep)) {
        const next = allocate(), splitting = id !== null && originalText.get(id) === currentText.get(id);
        const root: unknown = node.attrs["bindingRootId"];
        tr.setNodeMarkup(pos, undefined, { ...node.attrs, bindingId: next,
          ...(node.type.spec.attrs?.["bindingRootId"] ? { bindingRootId: splitting ? typeof root === "string" && root ? root : id : next } : {}) });
      }
    });
    return tr.docChanged ? tr : null;
  } });
}
