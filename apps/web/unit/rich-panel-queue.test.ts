import assert from "node:assert/strict";
import test from "node:test";
import { execFileSync } from "node:child_process";
import { AppliedIntentFailure } from "../src/rich/intent-queue";
import type { PanelCommand } from "../src/rich/synchronization";
import { panelHarness } from "./rich-panel-harness";
import { normalizeInline } from "../src/rich/normalize";
import { fromInline, toInline } from "../src/rich/inline";
import type { Content } from "../src/contracts/generated/rich_document_v1";

const add = (name: string, jobId: string | null = null): PanelCommand => ({ operation: "add", recordKind: "technology", jobId, values: { display: name } });
const clear: PanelCommand = { operation: "clear_technologies", recordKind: "technology", jobId: null, recordId: null, periodId: null, values: {} };
function gate() { let release = () => {}; const wait = new Promise<void>(resolve => { release = resolve; }); return { wait, release }; }

test("history treats an implicit field root and its engine round trip as the same identity", () => {
  const content: Content = [{ type: "fact_field", bindingId: "root", bindingRootId: null, recordId: "technology-a", fieldKey: "display",
    text: "A", syncedFactRevision: 1, styles: { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" } }];
  const roundTrip = fromInline(toInline(content), () => { throw new Error("No fragment expected"); });
  assert.deepEqual(normalizeInline(content), normalizeInline(roundTrip));
});

for (const scenario of ["pair", "clear", "duplicate", "mixed"] as const) test(`queued ${scenario} uses current revisions and exact Undo/Redo order`, { timeout: 30000 }, async context => {
  const entered = gate(), release = gate();
  const h = panelHarness({ preview: async count => { if (count === 1) { entered.release(); await release.wait; } } }); context.after(h.close);
  const a = h.intents.enqueue(add("Custom A")); await entered.wait;
  const second = scenario === "clear" ? clear : scenario === "duplicate" ? add("  custom   A ") : scenario === "mixed" ? add("Custom A", "job-1") : add("Custom B");
  const b = h.intents.enqueue(second); release.release(); await Promise.all([a, b]); await h.intents.drain();
  assert.equal(h.history.length, scenario === "duplicate" ? 1 : 2);
  assert.deepEqual(h.technologies(), scenario === "clear" ? [] : scenario === "pair" ? ["Custom A", "Custom B"] : ["Custom A"]);
  if (scenario === "mixed") assert.deepEqual(h.technologies("job-1"), ["Custom A"]);
  if (scenario !== "duplicate") { assert.ok(h.history.undo()); h.publish(); await h.queue.flush(); assert.deepEqual(h.technologies(), ["Custom A"]); }
  assert.ok(h.history.undo()); h.publish(); await h.queue.flush(); assert.deepEqual(h.technologies(), []);
  assert.ok(h.history.redo()); h.publish(); await h.queue.flush(); assert.deepEqual(h.technologies(), ["Custom A"]);
  if (scenario !== "duplicate") { assert.ok(h.history.redo()); h.publish(); await h.queue.flush(); }
  assert.equal(h.history.position, scenario === "duplicate" ? 1 : 2);
});

for (const failure of [1, 2]) test(`preview failure ${failure} keeps accepted edits without empty history markers`, { timeout: 15000 }, async context => {
  const h = panelHarness({ preview: async count => { if (count === failure) throw new Error("preview failed"); } }); context.after(h.close);
  const settled = await Promise.allSettled([h.intents.enqueue(add("A")), h.intents.enqueue(add("B")), h.intents.enqueue(add("C"))]);
  assert.equal(settled[failure - 1]?.status, "rejected"); assert.deepEqual(h.technologies(), failure === 1 ? [] : ["A"]);
  assert.equal(h.history.length, failure - 1); assert.equal(h.previews(), failure);
  await h.intents.enqueue(add("Retry")); assert.equal(h.history.length, failure);
});

test("save failure after panel apply recovers without another preview or action", { timeout: 15000 }, async context => {
  const h = panelHarness({ save: async count => { if (count === 1) throw new Error("disk full"); } }); context.after(h.close);
  await assert.rejects(h.intents.enqueue(add("Unsaved A")), AppliedIntentFailure);
  assert.deepEqual(h.technologies(), ["Unsaved A"]); assert.equal(h.history.length, 1); assert.equal(h.previews(), 1);
  await h.intents.drain(); assert.equal(h.previews(), 1); assert.equal(h.history.length, 1); assert.equal(h.saves(), 2);
  assert.ok(h.history.undo()); h.publish(); await h.queue.flush(); assert.deepEqual(h.technologies(), []);
});

test("closing a session fences a late panel reply and drops unsent requests", { timeout: 15000 }, async context => {
  const entered = gate(), release = gate();
  const h = panelHarness({ preview: async () => { entered.release(); await release.wait; } }); context.after(h.close);
  const settled = Promise.allSettled([h.intents.enqueue(add("A")), h.intents.enqueue(add("B"))]); await entered.wait;
  h.sync.close(); const closing = h.intents.close(); release.release(); await settled; await closing;
  assert.deepEqual(h.technologies(), []); assert.equal(h.history.length, 0); assert.equal(h.previews(), 1);
});

test("structured clear after Undo/Redo preserves the original prose and is one reversible action", { timeout: 30000 }, async context => {
  const workspace: unknown = JSON.parse(execFileSync(".venv/bin/python", ["-c", "import zipfile;print(zipfile.ZipFile('docs/gui/handoffs/PROTOTYPE-ADOPTION/fixtures/structured.foldcv').read('workspace.json').decode())"],
    { cwd: new URL("../../../", import.meta.url), encoding: "utf8" }));
  const h = panelHarness({ workspace }); context.after(h.close);
  const initial = h.technologies();
  await Promise.all([h.intents.enqueue(add("A")), h.intents.enqueue(add("B"))]);
  for (let count = 0; count < 2; count++) { assert.ok(h.history.undo()); h.publish(); await h.queue.flush(); }
  for (let count = 0; count < 2; count++) { assert.ok(h.history.redo()); h.publish(); await h.queue.flush(); }
  await Promise.all([h.intents.enqueue(add("C")), h.intents.enqueue(clear)]);
  assert.deepEqual(h.technologies(), []); assert.equal(h.history.length, 4);
  assert.ok(h.history.undo()); h.publish(); await h.queue.flush(); assert.deepEqual(h.technologies(), [...initial, "A", "B", "C"]);
  assert.ok(h.history.undo()); h.publish(); await h.queue.flush(); assert.deepEqual(h.technologies(), [...initial, "A", "B"]);
});
