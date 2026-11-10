import assert from "node:assert/strict";
import test from "node:test";
import { Schema, type Node } from "@tiptap/pm/model";
import { EditorState } from "@tiptap/pm/state";
import { DecorationSet, type Decoration } from "@tiptap/pm/view";
import { listEnds, listEndsPlugin } from "../src/rich/list-ends";

// The engine's node names; the plugin reads only the content node's type and text.
const schema = new Schema({ nodes: {
  doc: { content: "blockGroup" }, blockGroup: { content: "blockContainer+" },
  blockContainer: { content: "(paragraph | bulletListItem | numberedListItem) blockGroup?", attrs: { id: { default: "block" } } },
  paragraph: { content: "inline*" }, bulletListItem: { content: "inline*" }, numberedListItem: { content: "inline*" },
  text: { group: "inline" },
} });
const block = (kind: string, id: string, text: string, children?: Node[]) => schema.node("blockContainer", { id },
  [schema.node(kind, null, text ? schema.text(text) : []), ...(children ? [schema.node("blockGroup", null, children)] : [])]);
const paragraph = (id: string, text: string) => block("paragraph", id, text);
const bullet = (id: string, text: string, children?: Node[]) => block("bulletListItem", id, text, children);
const numbered = (id: string, text: string) => block("numberedListItem", id, text);

/** Each marked content node as its container's ID and its mark. */
function marks(doc: Node): [string, string][] {
  return listEnds(doc).map(({ from, to, end }) => {
    const content = doc.nodeAt(from);
    assert.ok(content && ["bulletListItem", "numberedListItem"].includes(content.type.name), "the mark sits on the item's content node");
    assert.equal(to, from + content.nodeSize);
    return [String(doc.resolve(from).parent.attrs["id"]), end];
  });
}

test("items get a semicolon, the last item of a list a full stop, and a paragraph between starts a new list", () => {
  const doc = schema.node("doc", null, schema.node("blockGroup", null, [
    bullet("a", "Первая"), bullet("b", "Вторая"), paragraph("p", "Между"), bullet("c", "Одна"),
  ]));
  assert.deepEqual(marks(doc), [["a", "item"], ["b", "last"], ["c", "last"]]);
});

test("an item closing itself keeps its own mark and still ends its list; an empty item gets none", () => {
  const doc = schema.node("doc", null, schema.node("blockGroup", null, [
    bullet("a", "Сделано"), bullet("b", "Стек:"), bullet("c", "Готово."), bullet("d", "  "), bullet("e", "Опыт и т.д."),
    bullet("f", "Ещё"), bullet("g", "Последняя."),
  ]));
  assert.deepEqual(marks(doc), [["a", "item"], ["f", "item"]]);
});

test("bullets and numbers are separate lists, and nested items form their own list", () => {
  const doc = schema.node("doc", null, schema.node("blockGroup", null, [
    bullet("a", "Пункт", [bullet("a1", "Вложенный"), bullet("a2", "Ещё вложенный")]), bullet("b", "Пункт два"),
    numbered("n1", "Первый"), numbered("n2", "Второй"),
  ]));
  assert.deepEqual(marks(doc), [["a1", "item"], ["a2", "last"], ["a", "item"], ["b", "last"], ["n1", "item"], ["n2", "last"]]);
});

test("the plugin decorates the items and follows document changes", () => {
  const doc = schema.node("doc", null, schema.node("blockGroup", null, [bullet("a", "Первая"), bullet("b", "Вторая")]));
  const plugin = listEndsPlugin(), state = EditorState.create({ schema, doc, plugins: [plugin] });
  const shown = plugin.props.decorations?.call(plugin, state);
  assert.ok(shown instanceof DecorationSet);
  const attribute = (item: Decoration) => (item as unknown as { type: { attrs?: Record<string, string> } }).type.attrs?.["data-fcv-list-end"];
  const widgets = shown.find().filter(item => (item.spec as { end?: string }).end !== undefined);
  assert.deepEqual(shown.find().filter(item => !(item.spec as { end?: string }).end).map(attribute), ["item", "last"]);
  assert.deepEqual(widgets.map(item => [(item.spec as { end: string }).end, item.from]), listEnds(doc).map(item => [item.end, item.to - 1]));
  assert.deepEqual(widgets.map(item => item.from), [9, 19], "the widget sits at the end of each item's text");
  const first = state.doc.firstChild?.firstChild;
  assert.ok(first);
  const next = state.apply(state.tr.delete(1, 1 + first.nodeSize));
  const after = plugin.props.decorations?.call(plugin, next);
  assert.ok(after instanceof DecorationSet && after.find().length === 2, "the item left alone closes the list");
  assert.deepEqual(marks(next.doc), [["b", "last"]]);
});
