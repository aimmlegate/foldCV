import assert from "node:assert/strict";
import test from "node:test";
import { errorMessage } from "../src/errors/messages";
import { harness } from "./support/template-harness";
import { TASK, at, caret, find, opened, press, select, sent, shown, texts, type, type Opened, type Shown } from "./support/e04-session";

// F3c and F3d of the tester feedback of 2026-11-23: typed text, Enter and pasted lines. Scenario e04, real Python service.
async function scenario(work: (current: Opened) => Promise<void>): Promise<void> {
  const value = await harness("e04");
  const current = await opened(value);
  try { await work(current); } finally { current.session.close(); await value.close(); }
}
const block = (current: Opened, id: string): Shown | undefined => shown(current.session).blocks.find(value => value.id === id);
const siblings = (current: Opened, id: string): Shown[] => {
  const blocks = shown(current.session).blocks, parent = blocks.find(value => value.id === id)?.parent;
  return blocks.filter(value => value.parent === parent);
};
function range(current: Opened, from: Shown, start: number, to: Shown, end: number): void {
  select(current.editor, at(current.editor, from.id, start), at(current.editor, to.id, end));
}
const bullets = (current: Opened) => shown(current.session).blocks.filter(value => value.text === TASK);

test("F3c point 1: a character typed over a range removes it and goes at the join; one Undo takes it back", () => scenario(async current => {
  const [first, second] = bullets(current);
  assert.ok(first && second);
  range(current, first, 12, second, 18);
  assert.equal(type(current.editor, current.session, "X"), true);
  await current.session.keyed();
  assert.equal(block(current, first.id)?.text, "Implemented Xprocessing");
  assert.deepEqual(caret(current.editor), [first.id, 13]);
  await current.session.navigate("undo");
  assert.deepEqual([block(current, first.id)?.text, block(current, second.id)?.text], [TASK, TASK]);
  assert.deepEqual(current.warnings, []);
}));

test("F3c point 2: characters typed while the range command runs are typed at the caret after it, in order", () => scenario(async current => {
  const [first, second] = bullets(current);
  assert.ok(first && second);
  range(current, first, 12, second, 18);
  assert.equal(type(current.editor, current.session, "a"), true);
  assert.equal(type(current.editor, current.session, "b"), true);
  assert.equal(type(current.editor, current.session, "c"), true);
  await current.session.keyed();
  await current.session.flush();
  assert.equal(block(current, first.id)?.text, "Implemented abcprocessing");
  assert.equal(sent(current.traffic, "remove_range"), 1);
  assert.deepEqual(current.warnings, []);
}));

test("F3c point 3: Enter over a selection in one line deletes it and splits there, as one action", () => scenario(async current => {
  const [first] = bullets(current);
  assert.ok(first);
  select(current.editor, at(current.editor, first.id, 11), at(current.editor, first.id, 17));
  assert.equal(press(current.editor, current.session, "Enter"), true);
  await current.session.keyed();
  const lines = siblings(current, first.id), index = lines.findIndex(value => value.id === first.id);
  assert.deepEqual([lines[index]?.text, lines[index + 1]?.text, lines[index + 1]?.type], ["Implemented", " processing", "bullet_list"]);
  assert.deepEqual(caret(current.editor), [lines[index + 1]?.id, 0]);
  await current.session.navigate("undo");
  assert.equal(block(current, first.id)?.text, TASK);
  assert.equal(siblings(current, first.id).length, lines.length - 1);
  assert.deepEqual(current.warnings, []);
}));

test("F3c point 4: Enter over a range removes it and splits at the join, as one action", () => scenario(async current => {
  const [first, second] = bullets(current);
  assert.ok(first && second);
  const count = siblings(current, first.id).length;
  range(current, first, 12, second, 18);
  assert.equal(press(current.editor, current.session, "Enter"), true);
  await current.session.keyed();
  const lines = siblings(current, first.id), index = lines.findIndex(value => value.id === first.id);
  assert.deepEqual([lines[index]?.text, lines[index + 1]?.text], ["Implemented ", "processing"]);
  assert.equal(lines.length, count, "one bullet less, one new bullet");
  await current.session.navigate("undo");
  assert.deepEqual([block(current, first.id)?.text, block(current, second.id)?.text], [TASK, TASK]);
  assert.deepEqual(current.warnings, []);
}));

test("F3c point 5: a composition that starts over a range collapses the selection to its end and removes nothing", () => scenario(async current => {
  const [first, second] = bullets(current);
  assert.ok(first && second);
  const before = texts(current.session);
  range(current, first, 12, second, 18);
  current.session.compositionStart();
  assert.deepEqual(caret(current.editor), [second.id, 18]);
  assert.equal(current.editor._tiptapEditor.state.selection.empty, true);
  current.session.compositionEnd();
  await current.session.flush();
  assert.deepEqual(texts(current.session), before);
  assert.equal(sent(current.traffic, "remove_range"), 0);
}));

test("F3d: three lines at the end of a bullet make three bullets; Undo, Redo and reopen", async () => {
  const value = await harness("e04");
  let current = await opened(value);
  try {
    const [first] = bullets(current);
    assert.ok(first);
    select(current.editor, at(current.editor, first.id, TASK.length));
    await current.session.pasteFrom(null, "one\ntwo\nthree");
    let lines = siblings(current, first.id), index = lines.findIndex(line => line.id === first.id);
    assert.deepEqual(lines.slice(index, index + 3).map(line => [line.text, line.type]),
      [[TASK + "one", "bullet_list"], ["two", "bullet_list"], ["three", "bullet_list"]]);
    assert.deepEqual(caret(current.editor), [lines[index + 2]?.id, 5]);
    assert.equal(sent(current.traffic, "paste_lines"), 1);
    await current.session.navigate("undo");
    assert.equal(block(current, first.id)?.text, TASK);
    await current.session.navigate("redo");
    current = await current.reopen();
    lines = siblings(current, first.id); index = lines.findIndex(line => line.id === first.id);
    assert.deepEqual(lines.slice(index, index + 3).map(line => line.text), [TASK + "one", "two", "three"]);
    assert.deepEqual(current.warnings, []);
  } finally { current.session.close(); await value.close(); }
});

test("F3d: lines into the middle of a line keep head, lines and tail in order; CR LF and blank lines", () => scenario(async current => {
  const employer = find(shown(current.session).blocks, "Example Labs");
  select(current.editor, at(current.editor, employer.id, 7));
  await current.session.pasteFrom(null, " one\r\n   \r\ntwo\rthree ");
  const lines = siblings(current, employer.id), index = lines.findIndex(line => line.id === employer.id);
  assert.deepEqual(lines.slice(index, index + 3).map(line => line.text), ["Example one", "two", "three  Labs"]);
  assert.deepEqual(lines.slice(index, index + 3).map(line => line.type), ["paragraph", "paragraph", "paragraph"]);
  assert.deepEqual(current.warnings, []);
}));

test("F3d: lines into an empty block, and over a selection in one block", () => scenario(async current => {
  const tasks = find(shown(current.session).blocks, "Tasks:");
  select(current.editor, at(current.editor, tasks.id, 0), at(current.editor, tasks.id, 6));
  await current.session.pasteFrom(null, "Done:\nLater:");
  let lines = siblings(current, tasks.id), index = lines.findIndex(line => line.id === tasks.id);
  assert.deepEqual(lines.slice(index, index + 2).map(line => line.text), ["Done:", "Later:"]);
  const later = lines[index + 1];
  assert.ok(later);
  select(current.editor, at(current.editor, later.id, 0), at(current.editor, later.id, 6));
  press(current.editor, current.session, "Backspace");
  await current.session.flush();
  select(current.editor, at(current.editor, later.id, 0));
  await current.session.pasteFrom(null, "a\nb");
  lines = siblings(current, tasks.id); index = lines.findIndex(line => line.id === later.id);
  assert.deepEqual(lines.slice(index, index + 2).map(line => line.text), ["a", "b"]);
  assert.deepEqual(current.warnings, []);
}));

test("F3d point 7: lines over the range of B1 remove it and go at the join, as one action", () => scenario(async current => {
  const [first, second] = bullets(current);
  assert.ok(first && second);
  range(current, first, 12, second, 18);
  await current.session.pasteFrom(null, "one\ntwo");
  const lines = siblings(current, first.id), index = lines.findIndex(line => line.id === first.id);
  assert.deepEqual(lines.slice(index, index + 2).map(line => line.text), ["Implemented one", "twoprocessing"]);
  assert.equal(sent(current.traffic, "remove_range"), 1);
  await current.session.navigate("undo");
  assert.deepEqual([block(current, first.id)?.text, block(current, second.id)?.text], [TASK, TASK]);
  assert.deepEqual(current.warnings, []);
}));

test("F3d point 8: a paste of more than 200 lines is refused with a text that names the limit", () => scenario(async current => {
  const [first] = bullets(current);
  assert.ok(first);
  const before = texts(current.session);
  select(current.editor, at(current.editor, first.id, TASK.length));
  await current.session.pasteFrom(null, Array.from({ length: 201 }, (_, index) => `line ${index}`).join("\n"));
  assert.deepEqual(texts(current.session), before);
  assert.deepEqual(current.warnings, [errorMessage("PASTE_TOO_LARGE")]);
  assert.match(errorMessage("PASTE_TOO_LARGE"), /200/u);
}));
