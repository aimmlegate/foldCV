import assert from "node:assert/strict";
import test from "node:test";
import { menuItems, type MenuState } from "../src/workbench/editor/context-menu";

// F5 of the tester feedback of 2026-11-23: the page's own menu shows only what can run.
const base: MenuState = { selection: "none", cuttable: false, editable: true, rewritable: false, rewordable: false, block: "b" };

test("no selection: paste and the block removal; «Переписать блок» only for a block that can be reworded", () => {
  assert.deepEqual(menuItems(base), ["paste", "removeBlock"]);
  assert.deepEqual(menuItems({ ...base, rewordable: true }), ["paste", "reword", "removeBlock"]);
});

test("a selection in one block: cut, copy, paste and «Изменить текст»", () => {
  assert.deepEqual(menuItems({ ...base, selection: "one", cuttable: true, rewritable: true }), ["cut", "copy", "paste", "rewrite", "removeBlock"]);
});

test("a selection over blocks: cut, copy and paste, no rewrite of a selection", () => {
  assert.deepEqual(menuItems({ ...base, selection: "range", cuttable: true, rewritable: true }), ["cut", "copy", "paste", "removeBlock"]);
  assert.deepEqual(menuItems({ ...base, selection: "blocks", cuttable: true }), ["cut", "copy", "paste", "removeBlock"]);
});

test("a technology line: no cut and no block removal", () => {
  assert.deepEqual(menuItems({ ...base, selection: "one", cuttable: false, block: null }), ["copy", "paste"]);
});

test("a read-only editor: copy only", () => {
  assert.deepEqual(menuItems({ ...base, editable: false, selection: "one", cuttable: true, rewritable: true, rewordable: true }), ["copy"]);
});

test("nothing applies: no item, so no menu opens", () => {
  assert.deepEqual(menuItems({ ...base, editable: false }), []);
});
