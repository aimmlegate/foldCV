import assert from "node:assert/strict";
import test from "node:test";
import { menuItems, wordAt, type MenuState } from "../src/workbench/editor/context-menu";

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

// Remark 3 after stop 4: a right click on a word selects it; the limits are the same on every engine.
test("the word at a place: Latin and Cyrillic words, numbers, hyphens, punctuation, the edges and no word", () => {
  const word = (text: string, offset: number) => { const found = wordAt(text, offset); return found && text.slice(found.start, found.end); };
  assert.equal(word("Backend engineer", 3), "Backend");
  assert.equal(word("Ведущий разработчик", 10), "разработчик");
  assert.equal(word("Опыт 3.5 года", 6), "3.5", "a decimal point inside a number");
  assert.equal(word("с 1,5 млн", 3), "1,5");
  assert.equal(word("Ростов-на-Дону, 2020", 8), "Ростов-на-Дону", "a hyphen between letters joins");
  assert.equal(word("e-mail — почта", 0), "e-mail");
  assert.equal(word("Python, Go.", 3), "Python", "a comma after the word stays out");
  assert.equal(word("«Kafka»", 3), "Kafka", "quotes around the word stay out");
  assert.equal(word("Kafka", 0), "Kafka", "the start of a container");
  assert.equal(word("Kafka", 5), "Kafka", "the end of a container takes the word before it");
  assert.equal(word("Go, Rust", 2), "Go", "right after the word: the word before the place");
  assert.equal(word("Go — Rust", 3), null, "a dash between spaces is no word");
  assert.equal(word("", 0), null, "an empty block");
  assert.equal(word("a - b", 2), null, "a free hyphen is no word");
  assert.equal(word("2017 — 2020", 2), "2017");
});
