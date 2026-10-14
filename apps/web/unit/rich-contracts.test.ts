import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { SessionHistory, type CellChange } from "../src/rich/history";
import { validateRichWorkspaceShape, validateWorkingFacts } from "../src/rich/validate";
import type { WorkingFacts } from "../src/contracts/generated/working_facts";

function fixture(): unknown { return JSON.parse(readFileSync(new URL("../../../tests/fixtures/rich_workspace.json", import.meta.url), "utf8")); }

test("rich wire fixtures preserve all content kinds and reject an unknown node", () => {
  const value = fixture();
  assert.equal(validateRichWorkspaceShape(value), true);
  if (!validateRichWorkspaceShape(value) || !value.project) throw new Error("Invalid fixture");
  assert.equal(value.schemaVersion, 6);
  assert.equal(value.project.schemaVersion, 5);
  assert.deepEqual(value.project.document.regions.map(region => region.role), ["header", "sidebar", "main"]);
  const block = value.project.document.regions[0]?.blocks[0];
  assert.ok(block);
  assert.equal(validateRichWorkspaceShape({ ...value, undoSlots: {} }), false);
  assert.equal(validateRichWorkspaceShape({ ...value, schemaVersion: 5 }), false);
  assert.equal(validateRichWorkspaceShape({ ...value, schemaVersion: 7 }), false);
  const unknownBlock: unknown = { ...block, type: "video" };
  const changed: unknown = { ...value, project: { ...value.project, document: {
    ...value.project.document, regions: value.project.document.regions.map((region, index) => index === 0 ? { ...region, blocks: [unknownBlock] } : region),
  } } };
  assert.equal(validateRichWorkspaceShape(changed), false);
});

function pythonMutation(facts: WorkingFacts, changes: readonly CellChange[]): WorkingFacts {
  const steps = changes.filter(change => change.key.startsWith("fact:")).map(change => {
    const before = facts.records.find(record => `fact:${record.id}` === change.key);
    if (!before || change.after === null) throw new Error("Invalid synthetic change");
    const record: unknown = JSON.parse(change.after);
    return { kind: "put_record", beforeRevision: before.revision, record };
  });
  const python = fileURLToPath(new URL("../../../.venv/bin/python", import.meta.url));
  const bridge = fileURLToPath(new URL("../../../tools/rich_history_bridge.py", import.meta.url));
  const response: unknown = JSON.parse(execFileSync(python, [bridge], {
    input: JSON.stringify({ facts, steps, actionId: "synthetic-history-apply" }), encoding: "utf8",
  }));
  if (typeof response !== "object" || response === null || !("facts" in response) || !validateWorkingFacts(response.facts)) throw new Error("Invalid Python result");
  return response.facts;
}

test("rich shared history applies Python fact mutations and inverses without another cursor", () => {
  const value = fixture();
  if (!validateRichWorkspaceShape(value) || !value.project) throw new Error("Invalid fixture");
  let facts = value.project.facts;
  const candidate = facts.records.find(record => record.kind === "candidate");
  assert.ok(candidate && candidate.kind === "candidate");
  const edited = { ...candidate, name: { ...candidate.name, value: "Sam Example", rawText: "Sam Example" } };
  const h = new SessionHistory("python-session", new Map([
    ["fact:candidate-1", JSON.stringify(candidate)], ["block:name", "Alex Example"], ["block:other", "Other work"],
  ]), changes => { if (changes.some(change => change.key.startsWith("fact:"))) facts = pythonMutation(facts, changes); });
  h.commit("typing", [{ key: "block:other", before: "Other work", after: "Independent typing" }]);
  h.commit("panel", [{ key: "fact:candidate-1", before: h.read("fact:candidate-1"), after: JSON.stringify(edited) },
    { key: "block:name", before: "Alex Example", after: "Sam Example" }]);
  assert.equal(facts.records[0]?.revision, 2);
  assert.equal(h.length, 2);
  assert.equal(h.undo(), true);
  assert.equal(h.read("block:other"), "Independent typing");
  const restored = facts.records[0];
  assert.ok(restored?.kind === "candidate");
  assert.equal(restored.name.value, "Alex Example");
  assert.equal(restored.name.revision, 3);
  assert.equal(h.redo(), true);
  assert.equal(facts.records[0]?.revision, 4);
  assert.equal(h.read("block:name"), "Sam Example");
  assert.equal(h.position, 2);
});
