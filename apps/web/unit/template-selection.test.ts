import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { BlockNoteEditor } from "@blocknote/core";
import { TextSelection, type EditorState } from "@tiptap/pm/state";
import { GapCursor } from "@tiptap/pm/gapcursor";
import { templateSchema } from "../src/rich/template-schema";
import { selectedTextBlocks, shownSelection } from "../src/rich/selection";
import { markable } from "../src/rich/v7-extraction";

register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { Toolbar } = await import("../src/workbench/editor/Toolbar");

/** Two item sections in a row, as Focus rows are: each has a hidden title line and one shown name. */
function opened() {
  const editor = BlockNoteEditor.create({ schema: templateSchema, initialContent: [
    { id: "title", type: "heading", content: "Focus" },
    { id: "first", type: "section", children: [{ id: "first-name", type: "paragraph", content: "Python" }] },
    { id: "second", type: "section", children: [{ id: "second-name", type: "paragraph", content: "Go" }] },
    { id: "table", type: "table", content: { type: "tableContent", rows: [{ cells: ["cell text"] }] } },
  ] });
  return editor._tiptapEditor.state;
}
/** The position just inside the text of a block's own line. */
function inside(state: EditorState, id: string): { start: number; end: number } {
  let found: { start: number; end: number } | null = null;
  state.doc.descendants((node, pos) => {
    if (found) return false;
    if (node.type.name === "blockContainer" && node.attrs["id"] === id) {
      const content = node.firstChild;
      assert.ok(content);
      found = { start: pos + 2, end: pos + 2 + content.content.size };
      return false;
    }
    return true;
  });
  assert.ok(found, id);
  return found;
}
function at(state: EditorState, anchor: number, head = anchor): EditorState {
  return state.apply(state.tr.setSelection(TextSelection.create(state.doc, anchor, head)));
}

test("a caret in a hidden section line moves on to shown text the way it went; a click goes into the item", () => {
  const state = opened(), hidden = inside(state, "second").start, previous = inside(state, "first-name"), next = inside(state, "second-name");
  const moved = at(state, hidden);
  assert.equal(moved.selection.$head.parent.type.name, "section");
  // Down from Python's end: into Go. Up from Go's start: back to Python's end. A click: into the item.
  assert.equal(shownSelection(at(state, previous.end).selection, moved)?.head, next.start);
  assert.equal(shownSelection(at(state, next.start).selection, moved)?.head, previous.end);
  assert.equal(shownSelection(null, moved)?.head, next.start);
  // A gap caret before an item, as → leaves it after a heading, goes on into the item too.
  const gap = state.apply(state.tr.setSelection(new GapCursor(state.doc.resolve(hidden - 1))));
  assert.equal(gap.selection instanceof GapCursor, true);
  assert.equal(shownSelection(at(state, previous.end).selection, gap)?.head, next.start);
  // A range from an item's line names whole items and stays; so does a caret in shown text.
  assert.equal(shownSelection(null, at(state, inside(state, "first").start, hidden)), null);
  assert.equal(shownSelection(null, at(state, next.start)), null);
});

test("block styles need a selected text block and inline styles a container Python addresses", () => {
  const state = opened();
  const section = at(state, inside(state, "second").start), name = inside(state, "second-name");
  let cell: [number, number] = [0, 0];
  state.doc.descendants((node, pos) => { if (node.isTextblock && node.textContent === "cell text") cell = [pos + 1, pos + 1 + node.content.size]; return true; });
  assert.deepEqual(selectedTextBlocks(section), [], "a hidden section line is no text block");
  assert.deepEqual(selectedTextBlocks(at(state, name.start)).map(block => block.id), ["second-name"]);
  assert.equal(markable(at(state, name.start, name.end)), true);
  assert.equal(markable(at(state, cell[0], cell[1])), false, "a table cell without its identity is not addressed");
  const markup = renderToStaticMarkup(createElement(Toolbar, { command: () => {}, textStyle: () => {}, factsVisible: false, canUndo: false,
    canRedo: false, selecting: false, blocks: false, marks: false, style: "p",
    active: { bold: false, italic: false, underline: false, list: false, numbered: false } }));
  for (const label of ["Стиль текста", "Полужирный", "Курсив", "Подчёркнутый", "Маркированный список", "Нумерованный список"])
    assert.match(markup, new RegExp(`aria-label="${label}"[^>]*disabled=""|disabled=""[^>]*aria-label="${label}"`, "u"), label);
});
