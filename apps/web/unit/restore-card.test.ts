import assert from "node:assert/strict";
import test from "node:test";
import { harness } from "./support/template-harness";
import { at, find, opened, press, select, shown, texts } from "./support/e04-session";

// F7 of the tester feedback of 2026-11-23 (D179): a removed card comes back from Facts after a reopen. Scenario e04.
test("F7: a removed job card is offered back after a reopen, comes back once in its place, and one Undo takes it back", async () => {
  const value = await harness("e04");
  let current = await opened(value);
  try {
    const before = texts(current.session);
    const { session, editor } = current;
    const blocks = shown(session).blocks, first = find(blocks, "Second Works"), last = find(blocks, "Role: engineer");
    const job = shown(session).response.workspace.project?.facts.records.find(record => record.kind === "employment"
      && "employer" in record && record.employer.rawText === "Second Works");
    assert.ok(job);
    select(editor, at(editor, first.id, 0), at(editor, last.id, last.text.length));
    press(editor, session, "Backspace");
    await session.flush();
    press(editor, session, "Backspace");
    await session.keyed();
    assert.equal(texts(session).includes("Second Works"), false, "the card is off the page");
    current = await current.reopen();
    const plan = shown(current.session).response.presentation?.editor ?? null;
    assert.deepEqual(plan?.offPage, [job.id], "Facts offers the card back");
    await current.session.panel({ operation: "restore", recordId: job.id });
    const back = texts(current.session);
    assert.deepEqual(back.filter(text => text === "Second Works" || text === "Role: engineer"), ["Second Works", "Role: engineer"]);
    assert.equal(back.indexOf("Second Works") > back.indexOf("Implemented queue processing"), true, "after the first job, as the import");
    assert.equal(shown(current.session).response.presentation?.editor?.offPage, undefined);
    await current.session.navigate("undo");
    assert.equal(texts(current.session).includes("Second Works"), false, "one Undo takes it back");
    assert.notDeepEqual(texts(current.session), before);
    assert.deepEqual(current.warnings, []);
  } finally { current.session.close(); await value.close(); }
});
