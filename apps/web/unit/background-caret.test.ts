import assert from "node:assert/strict";
import test from "node:test";
import { Schema, type Node } from "@tiptap/pm/model";
import { AllSelection, EditorState, TextSelection } from "@tiptap/pm/state";
import { captureCaret, restoreCaret } from "../src/rich/caret";

const schema = new Schema({ nodes: {
  doc: { content: "blockContainer+" },
  blockContainer: { content: "paragraph | table", attrs: { id: { default: "block" } } },
  paragraph: { content: "text*" }, table: { content: "tableRow+" }, tableRow: { content: "tableCell+" },
  tableCell: { content: "paragraph", attrs: { foldcvNodeId: { default: null } } }, text: {},
} });
const paragraph = (text: string) => schema.node("paragraph", null, text ? schema.text(text) : []);
const block = (id: string, text: string) => schema.node("blockContainer", { id }, paragraph(text));
const table = (cells: string[]) => schema.node("blockContainer", { id: "table" }, schema.node("table", null,
  schema.node("tableRow", null, cells.map(id => schema.node("tableCell", { foldcvNodeId: id }, paragraph("Same text"))))));
function position(doc: Node, id: string, offset: number, cell: string | null = null): number {
  let result: number | null = null;
  doc.descendants((node, pos) => {
    if (!node.isTextblock) return;
    const path = doc.resolve(pos + 1), ancestors = Array.from({ length: path.depth }, (_, i) => path.node(i + 1));
    if (ancestors.some(node => node.type.name === "blockContainer" && node.attrs["id"] === id)
      && (cell === null || ancestors.some(node => node.attrs["foldcvNodeId"] === cell))) result = pos + 1 + offset;
  });
  assert.notEqual(result, null); return result ?? 0;
}

test("whole-document adoption preserves a caret in its original block instead of the last table cell", () => {
  const before = schema.node("doc", null, [block("quote", "Quoted work with input"), table(["a", "b"])]);
  const state = EditorState.create({ schema, doc: before, selection: TextSelection.create(before, position(before, "quote", 21)) });
  const tr = state.tr, caret = captureCaret(tr), after = schema.node("doc", null, [block("quote", "Quoted work"), table(["a", "b"])]);
  tr.replaceWith(0, before.content.size, after.content); restoreCaret(tr, caret);
  assert.equal(tr.selection.anchor, position(after, "quote", 11)); assert.equal(tr.selection.head, tr.selection.anchor);
});

test("unrelated inserted content preserves a backward text selection by stable endpoints", () => {
  const before = schema.node("doc", null, [block("first", "First text"), block("second", "Second text")]);
  const state = EditorState.create({ schema, doc: before, selection: TextSelection.create(before, position(before, "second", 5), position(before, "first", 2)) });
  const tr = state.tr, caret = captureCaret(tr), after = schema.node("doc", null, [block("new", "New prefix"), before.child(0), before.child(1)]);
  tr.replaceWith(0, before.content.size, after.content); restoreCaret(tr, caret);
  assert.equal(tr.selection.anchor, position(after, "second", 5)); assert.equal(tr.selection.head, position(after, "first", 2));
});

test("table cell reorder with equal text preserves the selected cell identity and offset", () => {
  const before = schema.node("doc", null, [table(["a", "b"])]);
  const state = EditorState.create({ schema, doc: before, selection: TextSelection.create(before, position(before, "table", 4, "a")) });
  const tr = state.tr, caret = captureCaret(tr), after = schema.node("doc", null, [table(["b", "a"])]);
  tr.replaceWith(0, before.content.size, after.content); restoreCaret(tr, caret);
  assert.equal(tr.selection.anchor, position(after, "table", 4, "a"));
});

test("selection remains valid when an endpoint is deleted and select-all survives replacement", () => {
  const before = schema.node("doc", null, [block("first", "First text"), block("second", "Second text")]);
  const state = EditorState.create({ schema, doc: before, selection: TextSelection.create(before, position(before, "first", 2), position(before, "second", 3)) });
  const tr = state.tr, caret = captureCaret(tr), after = schema.node("doc", null, [before.child(0)]);
  tr.replaceWith(0, before.content.size, after.content); restoreCaret(tr, caret);
  assert.equal(tr.selection.anchor, position(after, "first", 2)); assert.equal(tr.selection.empty, true);
  tr.setSelection(new AllSelection(tr.doc)); const all = captureCaret(tr);
  tr.replaceWith(0, tr.doc.content.size, before.content); restoreCaret(tr, all);
  assert.ok(tr.selection instanceof AllSelection);
});
