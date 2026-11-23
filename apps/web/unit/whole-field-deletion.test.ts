import assert from "node:assert/strict";
import test from "node:test";
import { harness } from "./support/template-harness";
import { facts, fields, find, opened, press, selectText, shown } from "./support/e04-session";

// F3-0 of the tester feedback of 2026-11-23: a deletion of a field's whole text keeps the fact. Scenario e04.
test("F3-0: the whole employer text deleted keeps the fact; Backspace again removes the line; two Undo bring both back", async () => {
  const value = await harness("e04");
  let current = await opened(value);
  try {
    const { session, editor, warnings } = current;
    const line = find(shown(session).blocks, "Example Labs"), before = facts(session);
    selectText(editor, line);
    assert.equal(press(editor, session, "Backspace"), false, "a text selection is text input");
    await session.flush();
    let blocks = shown(session).blocks;
    const emptied = blocks.find(block => block.id === line.id);
    assert.deepEqual([emptied?.text, emptied?.parts], ["", []], "the block is empty: no fragment of the field stays");
    assert.equal(facts(session), before, "the fact records are equal before and after");
    assert.equal(press(editor, session, "Backspace"), true);
    await session.keyed();
    assert.equal(shown(session).blocks.some(block => block.id === line.id), false);
    await session.navigate("undo");
    assert.deepEqual(shown(session).blocks.find(block => block.id === line.id)?.parts, []);
    await session.navigate("undo");
    blocks = shown(session).blocks;
    const back = blocks.find(block => block.id === line.id);
    assert.equal(back?.text, "Example Labs");
    assert.deepEqual(fields(back).map(part => part["cellId"]), fields(line).map(part => part["cellId"]), "the fact field is back");
    assert.equal(facts(session), before);
    current = await current.reopen();
    assert.equal(shown(current.session).blocks.find(block => block.id === line.id)?.text, "Example Labs");
    assert.deepEqual(warnings, []);
  } finally { current.session.close(); await value.close(); }
});
