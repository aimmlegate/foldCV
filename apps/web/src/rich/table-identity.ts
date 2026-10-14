import { Extension } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey, type Transaction } from "@tiptap/pm/state";

export type TableRowIdentity = { id: string; cells: string[] };
const kinds = new Set(["tableRow", "tableCell", "tableHeader"]);
function id(node: PMNode): string | null {
  const value: unknown = node.attrs["foldcvNodeId"];
  return typeof value === "string" && value.length > 0 ? value : null;
}

export const tableIdentityAttributes = Extension.create({
  name: "foldcv-table-identities",
  addGlobalAttributes: () => [{ types: [...kinds], attributes: {
    foldcvNodeId: { default: null, parseHTML: (element: HTMLElement) => element.getAttribute("data-rich-node-id"),
      renderHTML: (attributes: Record<string, unknown>) => typeof attributes["foldcvNodeId"] === "string"
        ? { "data-rich-node-id": attributes["foldcvNodeId"] } : {} },
  } }],
});

export function tableIdentityPlugin(allocate: () => string = () => crypto.randomUUID()) {
  return new Plugin({ key: new PluginKey("foldcv-table-identities"), appendTransaction: (transactions, before, after) => {
    const positions = new Map<string, number[]>();
    after.doc.descendants((node, pos) => {
      if (kinds.has(node.type.name)) {
        const value = id(node);
        if (value) positions.set(value, [...(positions.get(value) ?? []), pos]);
      }
    });
    const originals = new Map<string, number>();
    before.doc.descendants((node, pos) => {
      const value = id(node);
      if (value && kinds.has(node.type.name)) {
        let mapped = pos;
        for (const transaction of transactions) mapped = transaction.mapping.map(mapped, 1);
        originals.set(value, mapped);
      }
    });
    const tr = after.tr.setMeta("foldcv.table.identities", true);
    after.doc.descendants((node, pos) => {
      if (!kinds.has(node.type.name)) return;
      const value = id(node);
      const candidates = value ? positions.get(value) ?? [] : [];
      const original = value ? originals.get(value) : undefined;
      const keep = original !== undefined && candidates.includes(original) ? original : candidates[0];
      if (!value || (candidates.length > 1 && pos !== keep)) {
        tr.setNodeMarkup(pos, undefined, { ...node.attrs, foldcvNodeId: allocate() });
      }
    });
    return tr.docChanged ? tr : null;
  } });
}

export function readTableIdentities(doc: PMNode): Map<string, TableRowIdentity[]> {
  const result = new Map<string, TableRowIdentity[]>();
  doc.descendants(node => {
    const blockId: unknown = node.attrs["id"];
    const table = node.firstChild;
    if (node.type.name !== "blockContainer" || typeof blockId !== "string" || table?.type.name !== "table") return;
    const rows: TableRowIdentity[] = [];
    table.forEach(row => {
      const rowId = id(row);
      if (!rowId) throw new Error("Uninitialized table row");
      const cells: string[] = [];
      row.forEach(cell => { const cellId = id(cell); if (!cellId) throw new Error("Uninitialized table cell"); cells.push(cellId); });
      rows.push({ id: rowId, cells });
    });
    result.set(blockId, rows);
  });
  return result;
}

export function restoreTableIdentities(tr: Transaction, tables: ReadonlyMap<string, readonly TableRowIdentity[]>): void {
  tr.doc.descendants((node, pos) => {
    const blockId: unknown = node.attrs["id"];
    const table = node.firstChild;
    if (node.type.name !== "blockContainer" || typeof blockId !== "string" || table?.type.name !== "table") return;
    const expected = tables.get(blockId);
    if (!expected) return;
    if (expected.length !== table.childCount) throw new Error("Table identity row mismatch");
    table.forEach((row, offset, index) => {
      const rowIds = expected[index];
      if (!rowIds || rowIds.cells.length !== row.childCount) throw new Error("Table identity cell mismatch");
      const rowPos = pos + 2 + offset;
      tr.setNodeMarkup(rowPos, undefined, { ...row.attrs, foldcvNodeId: rowIds.id });
      row.forEach((cell, cellOffset, cellIndex) => tr.setNodeMarkup(rowPos + 1 + cellOffset, undefined,
        { ...cell.attrs, foldcvNodeId: rowIds.cells[cellIndex] }));
    });
  });
}
