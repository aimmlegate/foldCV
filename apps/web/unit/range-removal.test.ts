import assert from "node:assert/strict";
import test from "node:test";
import { AllSelection } from "@tiptap/pm/state";
import { errorMessage } from "../src/errors/messages";
import { harness } from "./support/template-harness";
import { TASK, at, caret, facts, fields, find, opened, press, select, sent, shown, texts, type Opened, type Shown } from "./support/e04-session";

// F3b of the tester feedback of 2026-11-23: keys, cut and paste over a range that spans containers. Scenario e04.
async function scenario(work: (current: Opened) => Promise<void>): Promise<void> {
  const value = await harness("e04");
  const current = await opened(value);
  try { await work(current); } finally { current.session.close(); await value.close(); }
}
const block = (current: Opened, id: string): Shown | undefined => shown(current.session).blocks.find(value => value.id === id);
const bullets = (current: Opened) => shown(current.session).blocks.filter(value => value.text === TASK);
function range(current: Opened, from: Shown, start: number, to: Shown, end: number): void {
  select(current.editor, at(current.editor, from.id, start), at(current.editor, to.id, end));
}

test("F3b B1: Backspace over a range from bullet 1 to bullet 2 merges them; both cells stay distinct", () => scenario(async current => {
  const [first, second] = bullets(current);
  assert.ok(first && second);
  range(current, first, 12, second, 18);
  assert.equal(press(current.editor, current.session, "Backspace"), true);
  await current.session.keyed();
  const merged = block(current, first.id);
  assert.equal(merged?.text, "Implemented processing");
  assert.equal(block(current, second.id), undefined);
  assert.deepEqual(fields(merged).map(part => part["cellId"]), [fields(first)[0]?.["cellId"], fields(second)[0]?.["cellId"]]);
  assert.deepEqual(caret(current.editor), [first.id, 12], "the caret is at the join");
  assert.deepEqual(current.warnings, []);
}));

test("F3b B2: a range from the heading to the end of section 1 removes both; section 2 stays", () => scenario(async current => {
  const blocks = shown(current.session).blocks, heading = find(blocks, "PROJECTS");
  const [section, other] = blocks.filter(value => value.type === "section");
  assert.ok(section && other);
  const last = blocks.filter(value => value.parent === section.id).at(-1);
  assert.ok(last);
  range(current, heading, 0, last, last.text.length);
  assert.equal(press(current.editor, current.session, "Backspace"), true);
  await current.session.keyed();
  const after = shown(current.session).blocks;
  assert.equal(after.some(value => value.id === heading.id || value.id === section.id), false);
  assert.ok(after.some(value => value.id === other.id));
  assert.deepEqual(caret(current.editor), [find(after, "Second Works").id, 0], "no block before: the start of the next one");
  assert.deepEqual(current.warnings, []);
}));

test("F3b B3: a paste over a range: one block, the employer fact takes the cut and the text; one Undo brings both lines back", () => scenario(async current => {
  const blocks = shown(current.session).blocks, employer = find(blocks, "Second Works"), role = find(blocks, "Role: engineer");
  range(current, employer, 2, role, 4);
  await current.session.pasteFrom(null, "new words");
  assert.equal(block(current, employer.id)?.text, "Senew words: engineer");
  assert.equal(block(current, role.id), undefined);
  const record = current.session.queue.template.durable.workspace.project?.facts.records.find(value => value.kind === "employment"
    && JSON.stringify(value).includes("Senew words"));
  assert.ok(record, "the employer fact reads «Senew words»");
  assert.deepEqual(caret(current.editor), [employer.id, "Senew words".length]);
  await current.session.navigate("undo");
  assert.equal(block(current, employer.id)?.text, "Second Works");
  assert.equal(block(current, role.id)?.text, "Role: engineer");
  assert.deepEqual(current.warnings, []);
}));

test("F3b B4: a range from card 1 to card 2 removes the lines between and does not merge", () => scenario(async current => {
  const blocks = shown(current.session).blocks, role = find(blocks, "Role: Backend Engineer"), employer = find(blocks, "Second Works");
  range(current, role, 6, employer, 2);
  assert.equal(press(current.editor, current.session, "Backspace"), true);
  await current.session.keyed();
  const after = shown(current.session).blocks;
  assert.equal(block(current, role.id)?.text, "Role: ");
  assert.equal(block(current, employer.id)?.text, "cond Works");
  assert.equal(block(current, employer.id)?.parent, employer.parent);
  assert.equal(after.some(value => value.text === TASK || value.text === "Tasks:"), false);
  assert.deepEqual(current.warnings, []);
}));

test("F3b B5: a range over the date and technology lines joins the edges; the technology fact stays", () => scenario(async current => {
  const blocks = shown(current.session).blocks, employer = find(blocks, "Example Labs"), role = find(blocks, "Role: Backend Engineer");
  const before = current.session.queue.template.durable.workspace.project?.facts.records.find(value => value.kind === "technology");
  range(current, employer, 5, role, 4);
  assert.equal(press(current.editor, current.session, "Delete"), true);
  await current.session.keyed();
  assert.equal(block(current, employer.id)?.text, "Examp: Backend Engineer");
  assert.equal(texts(current.session).some(text => text === "Python" || text === "03.2020–11.2023"), false);
  const after = current.session.queue.template.durable.workspace.project?.facts.records.find(value => value.kind === "technology");
  assert.deepEqual(after, before);
  assert.deepEqual(current.warnings, []);
}));

test("F3b B6: an edge that cuts the technology line is refused with the technology text, from each side", () => scenario(async current => {
  const blocks = shown(current.session).blocks, employer = find(blocks, "Example Labs"), python = find(blocks, "Python");
  const role = find(blocks, "Role: Backend Engineer"), before = JSON.stringify(blocks);
  range(current, employer, 3, python, 2);
  assert.equal(press(current.editor, current.session, "Backspace"), true);
  range(current, python, 2, role, 4);
  assert.equal(press(current.editor, current.session, "Backspace"), true);
  await current.session.keyed();
  assert.equal(JSON.stringify(shown(current.session).blocks), before, "no change");
  assert.deepEqual(current.warnings, [errorMessage("TECHNOLOGY_IN_FACTS"), errorMessage("TECHNOLOGY_IN_FACTS")]);
}));

test("F3b B7: B1, then Undo, Redo and reopen keep the ids", async () => {
  const value = await harness("e04");
  let current = await opened(value);
  try {
    const [first, second] = bullets(current);
    assert.ok(first && second);
    range(current, first, 12, second, 18);
    press(current.editor, current.session, "Backspace");
    await current.session.keyed();
    await current.session.navigate("undo");
    assert.equal(block(current, first.id)?.text, TASK);
    assert.equal(block(current, second.id)?.text, TASK);
    await current.session.navigate("redo");
    assert.equal(block(current, first.id)?.text, "Implemented processing");
    current = await current.reopen();
    assert.equal(block(current, first.id)?.text, "Implemented processing");
    assert.equal(block(current, second.id), undefined);
    assert.deepEqual(current.warnings, []);
  } finally { current.session.close(); await value.close(); }
});

test("F3b B8: a cut over the range of B1 gives the plain text of two lines and removes the range (session.cutRange)", () => scenario(async current => {
  const [first, second] = bullets(current);
  assert.ok(first && second);
  range(current, first, 12, second, 18);
  const cut = current.session.cutRange();
  assert.ok(cut);
  assert.equal(cut.text, "queue processing\nImplemented queue ");
  await cut.done;
  assert.equal(block(current, first.id)?.text, "Implemented processing");
  assert.equal(sent(current.traffic, "remove_range"), 1);
  assert.deepEqual(current.warnings, []);
}));

test("F3b B9: ⌘A and Backspace leave one empty block with the caret; one Undo brings all back", () => scenario(async current => {
  const before = shown(current.session).blocks, view = current.editor._tiptapEditor.view;
  view.dispatch(view.state.tr.setSelection(new AllSelection(view.state.doc)));
  assert.equal(press(current.editor, current.session, "Backspace"), true);
  await current.session.keyed();
  const after = shown(current.session).blocks;
  assert.deepEqual(after.map(value => [value.id, value.text]), [[find(before, "PROJECTS").id, ""]]);
  assert.deepEqual(caret(current.editor), [find(before, "PROJECTS").id, 0]);
  await current.session.navigate("undo");
  assert.deepEqual(shown(current.session).blocks.map(value => [value.id, value.text]), before.map(value => [value.id, value.text]));
  assert.deepEqual(current.warnings, []);
}));

test("F3b B10: two Backspace keys on a range with no wait make one removal and no warning", () => scenario(async current => {
  const [first, second] = bullets(current);
  assert.ok(first && second);
  const records = facts(current.session);
  range(current, first, 1, second, 3);
  assert.equal(press(current.editor, current.session, "Backspace"), true);
  assert.equal(press(current.editor, current.session, "Backspace"), true);
  await current.session.keyed();
  assert.equal(sent(current.traffic, "remove_range"), 1);
  assert.equal(block(current, first.id)?.text, "Ilemented queue processing");
  assert.notEqual(facts(current.session), records);
  assert.deepEqual(current.warnings, []);
}));
