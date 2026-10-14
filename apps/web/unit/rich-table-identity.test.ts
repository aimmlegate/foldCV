import assert from "node:assert/strict";
import test from "node:test";
import { Schema, type Node as PMNode } from "@tiptap/pm/model";
import { EditorState } from "@tiptap/pm/state";
import { readTableIdentities, restoreTableIdentities, tableIdentityPlugin } from "../src/rich/table-identity";

const schema = new Schema({ nodes: {
  doc: { content: "blockContainer+" },
  blockContainer: { content: "table", attrs: { id: { default: "table-1" } } },
  table: { content: "tableRow+" },
  tableRow: { content: "tableCell+", attrs: { foldcvNodeId: { default: null } } },
  tableCell: { content: "text*", attrs: { foldcvNodeId: { default: null } } },
  text: {},
} });
function fixture() {
  const cell = () => schema.node("tableCell", null, schema.text("same"));
  const row = () => schema.node("tableRow", null, [cell(), cell()]);
  const doc = schema.node("doc", null, schema.node("blockContainer", { id: "table-1" }, schema.node("table", null, [row(), row()])));
  let sequence = 0;
  const state = EditorState.create({ schema, doc, plugins: [tableIdentityPlugin(() => `node-${++sequence}`)] });
  return state.applyTransaction(state.tr.setMeta("initialize", true)).state;
}
function rows(state: EditorState) { return readTableIdentities(state.doc).get("table-1") ?? []; }
function nodePositions(doc: PMNode, type: string): number[] {
  const result: number[] = [];
  doc.descendants((node, pos) => { if (node.type.name === type) result.push(pos); });
  return result;
}

test("rich table identities survive text edits and row reorder with equal cell text", () => {
  let state = fixture();
  const original = rows(state);
  assert.equal(original.length, 2);
  assert.equal(new Set(original.flatMap(row => [row.id, ...row.cells])).size, 6);
  const text = nodePositions(state.doc, "text")[0];
  assert.ok(text !== undefined);
  state = state.applyTransaction(state.tr.insertText("!", text)).state;
  assert.deepEqual(rows(state), original);
  const block = state.doc.firstChild, table = block?.firstChild;
  assert.ok(block && table);
  const reversed = schema.node("doc", null, schema.node("blockContainer", { id: "table-1" },
    schema.node("table", null, [table.child(1), table.child(0)])));
  state = state.applyTransaction(state.tr.replaceWith(0, state.doc.content.size, reversed.content)).state;
  assert.deepEqual(rows(state), [...original].reverse());
});

test("rich pasted duplicate rows get fresh ids while the mapped original keeps its ids", () => {
  let state = fixture();
  const original = rows(state);
  const rowNode = state.doc.firstChild?.firstChild?.firstChild;
  const pos = nodePositions(state.doc, "tableRow")[0];
  assert.ok(rowNode && pos !== undefined);
  state = state.applyTransaction(state.tr.insert(pos, rowNode)).state;
  const after = rows(state);
  assert.deepEqual(after[1], original[0]);
  assert.deepEqual(after[2], original[1]);
  assert.equal(new Set(after.flatMap(row => [row.id, ...row.cells])).size, 9);
  assert.notEqual(after[0]?.id, original[0]?.id);
});

test("rich table inverse restores captured ids through public transactions", () => {
  let state = fixture();
  const original = rows(state);
  const block = state.doc.firstChild, table = block?.firstChild;
  assert.ok(block && table);
  const replacement = schema.node("blockContainer", { id: "table-1" }, schema.node("table", null, [
    schema.node("tableRow", null, [schema.node("tableCell", null, schema.text("new")), schema.node("tableCell", null, schema.text("value"))]),
    table.child(1),
  ]));
  const tr = state.tr.replaceWith(0, state.doc.content.size, replacement);
  restoreTableIdentities(tr, new Map([["table-1", original]]));
  state = state.applyTransaction(tr).state;
  assert.deepEqual(rows(state), original);
});
