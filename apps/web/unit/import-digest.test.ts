import assert from "node:assert/strict";
import test from "node:test";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { fields, title, needsCheck } from "../src/rich/fact-fields";
import { panelHarness } from "./rich-panel-harness";

test("digest notes save, edit, remove and undo without replacing resume paragraphs", { timeout: 20000 }, async context => {
  const workspace: unknown = structuredClone(fixture);
  assert.ok(validateRichWorkspaceShape(workspace) && workspace.project);
  workspace.project.facts.mode = "digest";
  const h = panelHarness({ workspace }); context.after(h.close);
  const document = structuredClone(h.document());
  await h.intents.enqueue({ operation: "add", recordKind: "claim", values: { value: "Вероятно Orion; роль не указана." } });
  let note = h.facts().records.at(-1); assert.ok(note?.kind === "claim");
  const id = note.id;
  assert.equal(h.facts().mode, "digest");
  assert.equal(fields(note)[0]?.text, "Вероятно Orion; роль не указана.");
  await h.intents.enqueue({ operation: "edit", recordId: id, values: { value: "Orion: Python API. Роль требует уточнения." } });
  note = h.facts().records.at(-1); assert.ok(note?.kind === "claim");
  assert.equal(title(note), "Orion: Python API. Роль требует уточнения.");
  await h.intents.enqueue({ operation: "remove", recordId: id });
  assert.equal(h.facts().records.some(record => record.id === id), false);
  assert.deepEqual(h.document(), document);
  assert.ok(h.history.undo()); h.publish(); await h.queue.flush();
  note = h.facts().records.at(-1); assert.ok(note?.kind === "claim");
  assert.equal(note.value.rawText, "Orion: Python API. Роль требует уточнения.");
  assert.ok(h.history.undo()); h.publish(); await h.queue.flush();
  note = h.facts().records.at(-1); assert.ok(note?.kind === "claim");
  assert.equal(note.value.rawText, "Вероятно Orion; роль не указана.");
  assert.ok(h.history.undo()); h.publish(); await h.queue.flush();
  assert.equal(h.facts().records.some(record => record.id === id), false);
  assert.equal(h.facts().mode, "digest");
  assert.deepEqual(h.document(), document);
});

test("fact warnings distinguish current labels and registry misses from unresolved source values", () => {
  const known = (rawText: string) => ({ rawText, value: rawText, status: "known" });
  const unresolved = (rawText: string) => ({ rawText, value: null, status: "unresolved" });
  const period = { start: known("2021-07"), present: { ...known("н.в."), value: true }, end: unresolved("н.в.") };
  assert.equal(needsCheck(period), false);
  assert.equal(needsCheck({ ...period, end: unresolved("примерно сейчас") }), true);
  assert.equal(needsCheck({ ...period, end: known("2025-03") }), true);
  assert.equal(needsCheck({ ...period, start: unresolved("весна 2021") }), true);
  const technology = { kind: "technology", display: known("Custom source skill"), canonicalId: unresolved("Custom source skill") };
  assert.equal(needsCheck(technology), false);
  assert.equal(needsCheck({ ...technology, display: unresolved("Unclear skill?") }), true);
});
