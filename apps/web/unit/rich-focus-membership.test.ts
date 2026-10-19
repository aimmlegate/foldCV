import assert from "node:assert/strict";
import test from "node:test";
import { execFileSync } from "node:child_process";
import { panelHarness } from "./rich-panel-harness";

test("Focus add/remove uses shared Undo/Redo and never starts narrative sync", { timeout: 30000 }, async context => {
  const workspace: unknown = JSON.parse(execFileSync(".venv/bin/python", ["-c",
    "from tests.recovery.test_focus_membership import workspace;print(workspace().model_dump_json(by_alias=True))"],
  { cwd: new URL("../../../", import.meta.url), encoding: "utf8" }));
  const h = panelHarness({ workspace }); context.after(h.close);
  const originalFetch = globalThis.fetch, paths: string[] = [];
  globalThis.fetch = async (input, init) => { paths.push(String(input)); return originalFetch(input, init); };
  const facts = h.facts();
  const ids = facts.records.filter(record => record.kind === "technology").map(record => record.id);
  const entries = () => h.document().regions[1].blocks.flatMap(block => block.type === "section" && block.props.presentation === "focus" ? block.children : [])
    .flatMap(block => Array.isArray(block.content) ? block.content.filter(span => span.type === "fact_field").map(span => span.text) : []);
  assert.deepEqual(entries(), ["Docker", "Python", "Linux"]);
  for (const recordId of ids) await h.intents.enqueue({ operation: "remove_from_focus", recordId });
  assert.deepEqual(h.document().regions[1].blocks, []);
  assert.deepEqual(h.facts(), facts);
  assert.equal(h.history.length, 3);
  assert.ok(h.history.undo()); h.publish(); await h.queue.flush();
  assert.deepEqual(entries(), ["Linux"]);
  assert.ok(h.history.redo()); h.publish(); await h.queue.flush();
  assert.deepEqual(entries(), []);
  const docker = ids[0]; assert.ok(docker);
  await h.intents.enqueue({ operation: "add_to_focus", recordId: docker });
  assert.deepEqual(entries(), ["Docker"]);
  assert.ok(h.history.undo()); h.publish(); await h.queue.flush();
  assert.deepEqual(entries(), []);
  assert.ok(h.history.redo()); h.publish(); await h.queue.flush();
  assert.deepEqual(entries(), ["Docker"]);
  assert.deepEqual(h.facts(), facts);
  assert.ok(paths.every(path => path.endsWith("/panel/preview")), "Membership must only call the deterministic preview endpoint");
});
