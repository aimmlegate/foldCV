import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import type { RichDocumentV1 } from "../src/contracts/generated/rich_document_v1";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { copyBlock, moveBlock, mergeBlocks } from "../src/rich/structure";
import { fromTable, toTable } from "../src/rich/table";
import { SessionHistory } from "../src/rich/history";

function fixture(): RichDocumentV1 {
  const raw: unknown = JSON.parse(readFileSync(new URL("../../../tests/fixtures/rich_workspace.json", import.meta.url), "utf8"));
  if (!validateRichWorkspaceShape(raw) || !raw.project) throw new Error("Bad fixture");
  return raw.project.document;
}

test("structural move keeps block identity and children while a copy has fresh node and field identities", () => {
  const doc = fixture(), original = doc.regions[2].blocks.find(block => block.type === "section");
  assert.ok(original && original.type === "section");
  const moved = moveBlock(doc, original.id, "sidebar");
  assert.deepEqual(moved.regions[1].blocks.at(-1), original);
  assert.deepEqual(doc.regions[2].blocks.find(block => block.id === original.id), original);
  let sequence = 0; const copy = copyBlock(original, () => `copy-${++sequence}`);
  assert.equal(copy.type, "section");
  if (copy.type !== "section") throw new Error("Expected section");
  assert.equal(copy.props.recordId, null); assert.notEqual(copy.id, original.id);
  const originals = new Set<string>(); const ids = (block: typeof original) => { originals.add(block.id); for (const child of block.children) originals.add(child.id); };
  ids(original); assert.ok(copy.children.every(child => !originals.has(child.id)));
  const originalFields = original.content.filter(span => span.type === "fact_field");
  const copiedFields = copy.content.filter(span => span.type === "fact_field");
  assert.deepEqual(copiedFields.map(span => span.recordId), originalFields.map(span => span.recordId));
  assert.ok(copiedFields.every(span => !originalFields.some(old => old.bindingId === span.bindingId)));
  assert.throws(() => moveBlock(doc, original.id, original.children[0]?.id ?? original.id), /TARGET_INVALID/);
});

test("table cells retain widths headers spans marks and ids across the public editor representation", () => {
  const table = fixture().regions[2].blocks.find(block => block.type === "table");
  assert.ok(table && table.type === "table");
  const identities = table.content.rows.map(row => ({ id: row.id, cells: row.cells.map(cell => cell.id) }));
  const before = toTable(table.content);
  const after = fromTable(before, identities, table.content, () => "unused");
  assert.deepEqual(after.rows.map(row => ({ id: row.id, cells: row.cells.map(cell => cell.id) })), identities);
  assert.deepEqual(after.columnWidths, table.content.columnWidths);
  assert.deepEqual(toTable(after), before);
  const copied = copyBlock(table); assert.ok(copied.type === "table");
  assert.notEqual(copied.content.rows[0].id, table.content.rows[0].id);
  assert.ok(copied.content.rows[0].cells.every(cell => !table.content.rows[0].cells.some(old => old.id === cell.id)));
});

test("abandoning a redo branch drops only its retained image values", () => {
  const history = new SessionHistory("session", new Map([["image", null]]));
  history.commit("structure", [{ key: "image", before: null, after: "asset-a" }]);
  history.commit("structure", [{ key: "image", before: "asset-a", after: "asset-b" }]);
  assert.ok(history.undo()); assert.ok(history.retainedValues().includes("asset-b"));
  history.commit("typing", [{ key: "text", before: null, after: "new branch" }]);
  assert.ok(!history.retainedValues().includes("asset-b")); assert.ok(history.retainedValues().includes("asset-a"));
  assert.equal(history.redo(), false);
});

test("merging text keeps destination identity marks children and both source citations", () => {
  const doc = fixture(), first = doc.regions[0].blocks[0]; assert.ok(first && Array.isArray(first.content));
  const copy = copyBlock(first); copy.id = "tail";
  if (!Array.isArray(copy.content)) throw new Error("Expected text");
  copy.content = [{ type: "text", text: " tail", styles: { italic: true } }];
  copy.provenance = [{ kind: "citation", id: "tail-citation", recordId: "candidate", fieldKeys: [], evidence: [] }];
  doc.regions[0].blocks.push(copy);
  const merged = mergeBlocks(doc, first.id, copy.id), destination = merged.regions[0].blocks.find(block => block.id === first.id);
  assert.ok(destination && Array.isArray(destination.content));
  assert.deepEqual(destination.content.slice(0, first.content.length), first.content);
  assert.deepEqual(destination.content.at(-1), copy.content[0]);
  assert.ok(destination.provenance.some(link => link.id === "tail-citation"));
  assert.equal(merged.regions[0].blocks.some(block => block.id === copy.id), false);
  assert.equal(doc.regions[0].blocks.some(block => block.id === copy.id), true);
});
