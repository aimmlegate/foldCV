import assert from "node:assert/strict";
import test from "node:test";
import { Schema, type Node } from "@tiptap/pm/model";
import { EditorState } from "@tiptap/pm/state";
import { DecorationSet } from "@tiptap/pm/view";
import { listIndexes, listIndexPlugin } from "../src/rich/list-index";

// The engine's node names; the plugin reads only the content node's type and its `start`.
const schema = new Schema({ nodes: {
  doc: { content: "blockGroup" }, blockGroup: { content: "blockContainer+" },
  blockContainer: { content: "(paragraph | numberedListItem) blockGroup?", attrs: { id: { default: "block" } } },
  paragraph: { content: "inline*" }, numberedListItem: { content: "inline*", attrs: { start: { default: undefined } } },
  text: { group: "inline" },
} });
const paragraph = (id: string, text: string) => schema.node("blockContainer", { id }, schema.node("paragraph", null, schema.text(text)));
const item = (id: string, text: string, start?: number, children?: Node[]) => schema.node("blockContainer", { id },
  [schema.node("numberedListItem", start === undefined ? null : { start }, schema.text(text)), ...(children ? [schema.node("blockGroup", null, children)] : [])]);

/** Each numbered content node as its container's ID and its number. */
function numbers(doc: Node): [string, number][] {
  return listIndexes(doc).map(({ from, to, index }) => {
    const content = doc.nodeAt(from);
    assert.equal(content?.type.name, "numberedListItem", "the number sits on the item's content node");
    assert.equal(to, from + (content?.nodeSize ?? 0));
    return [String(doc.resolve(from).parent.attrs["id"]), index];
  });
}

test("items count on from the one before them, restart after another block and take their own start", () => {
  const doc = schema.node("doc", null, schema.node("blockGroup", null, [
    item("a", "First"), item("b", "Second"), paragraph("p", "Between"), item("c", "Again first"), item("d", "Seven", 7), item("e", "Eight"),
  ]));
  assert.deepEqual(numbers(doc), [["a", 1], ["b", 2], ["c", 1], ["d", 7], ["e", 8]]);
});

test("items nested under an item count on their own, and the plugin follows document changes", () => {
  const doc = schema.node("doc", null, schema.node("blockGroup", null, [
    item("a", "Outer", undefined, [item("a1", "Inner"), item("a2", "Inner two")]), item("b", "Outer two"),
  ]));
  assert.deepEqual(numbers(doc), [["a", 1], ["a1", 1], ["a2", 2], ["b", 2]]);
  const plugin = listIndexPlugin(), state = EditorState.create({ schema, doc, plugins: [plugin] });
  const shown = plugin.props.decorations?.call(plugin, state);
  assert.ok(shown instanceof DecorationSet && shown.find().length === 4);
  const outer = state.doc.firstChild?.firstChild;
  assert.ok(outer);
  const next = state.apply(state.tr.delete(1, 1 + outer.nodeSize));
  const after = plugin.props.decorations?.call(plugin, next);
  assert.ok(after instanceof DecorationSet && after.find().length === 1, "the removed item and its children leave the numbering");
  assert.deepEqual(numbers(next.doc), [["b", 1]]);
});
