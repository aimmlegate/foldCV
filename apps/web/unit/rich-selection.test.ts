import assert from "node:assert/strict";
import test from "node:test";
import { Schema } from "@tiptap/pm/model";
import { EditorState, TextSelection } from "@tiptap/pm/state";
import { selectedRange, selectionLocation } from "../src/rich/selection";

const schema = new Schema({ nodes: {
  doc: { content: "blockGroup" }, blockGroup: { content: "blockContainer+" },
  blockContainer: { content: "paragraph | table", attrs: { id: { default: "block" } } },
  table: { content: "tableRow+" }, tableRow: { content: "tableCell+" },
  tableCell: { content: "paragraph", attrs: { foldcvNodeId: { default: "cell" } } },
  paragraph: { content: "inline*" }, factField: { inline: true, group: "inline", content: "text*" },
  hardBreak: { inline: true, group: "inline" }, text: { group: "inline" },
} });

for (const table of [false, true]) for (const field of [false, true]) for (const backwards of [false, true]) {
  test(`serialized selection retains newlines and UTF-16 offsets table=${table} field=${field} backwards=${backwards}`, () => {
    const name = field ? schema.node("factField", null, schema.text("A😀")) : schema.text("A😀");
    const paragraph = schema.node("paragraph", null, [name, schema.node("hardBreak"), schema.text("works daily")]);
    const content = table ? schema.node("table", null, schema.node("tableRow", null, schema.node("tableCell", null, paragraph))) : paragraph;
    const doc = schema.node("doc", null, schema.node("blockGroup", null, schema.node("blockContainer", null, content)));
    let from = 0;
    doc.descendants((node, pos) => { if (node.isText && node.text === "works daily") from = pos; });
    const tr = EditorState.create({ schema, doc }).tr.setSelection(TextSelection.create(doc, backwards ? from + 5 : from, backwards ? from : from + 5));
    const selected = selectedRange(tr);
    assert.ok(selected);
    assert.deepEqual([selected.anchor.offset, selected.head.offset], [4, 9]);
    assert.equal("A😀\nworks daily".slice(selected.anchor.offset, selected.head.offset), "works");
    assert.equal(selected.anchor.cellId, table ? "cell" : null);
    const caret = tr.setSelection(TextSelection.create(doc, from));
    assert.equal(selectedRange(caret), null);
    assert.equal(selectionLocation(caret), JSON.stringify(["block", table ? "cell" : null]));
  });
}

test("selection location distinguishes paragraphs and table cells without treating caret movement as a new paragraph", () => {
  const paragraph = (text: string) => schema.node("paragraph", null, schema.text(text));
  const doc = schema.node("doc", null, schema.node("blockGroup", null, [
    schema.node("blockContainer", { id: "first" }, paragraph("first")),
    schema.node("blockContainer", { id: "second" }, schema.node("table", null, schema.node("tableRow", null, [
      schema.node("tableCell", { foldcvNodeId: "a" }, paragraph("cell-a")),
      schema.node("tableCell", { foldcvNodeId: "b" }, paragraph("cell-b")),
    ]))),
  ]));
  const positions: number[] = [];
  doc.descendants((node, pos) => { if (node.isText) positions.push(pos); });
  const state = EditorState.create({ schema, doc });
  const locations = positions.map(pos => selectionLocation(state.tr.setSelection(TextSelection.create(doc, pos))));
  assert.deepEqual(locations, ['["first",null]', '["second","a"]', '["second","b"]']);
  assert.equal(selectionLocation(state.tr.setSelection(TextSelection.create(doc, positions[0]! + 2))), locations[0]);
});
