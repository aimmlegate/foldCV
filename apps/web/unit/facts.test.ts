import assert from "node:assert/strict";
import { test } from "node:test";
import sourceFixture from "../../../contracts/examples/extract_result.json" with { type: "json" };
import { validateExtractResult, validateFactSheet } from "../src/contracts/validate";
import { FactWorkflow } from "../src/facts/workflow";
import type { ImportedSource } from "../src/import/workflow";

if (!validateExtractResult(sourceFixture)) throw new Error("broken fixture");
const entry: ImportedSource = { result: sourceFixture, overlays: {} };

function sheet(sources: ImportedSource[]) {
  return { transportVersion: 1, sourceFingerprint: "synthetic", revision: 1, facts: [], employment: [],
    proposedFactIds: [], overlayFactRefs: {}, candidates: [], issues: [],
    units: sources.flatMap((source) => source.result.units.map((unit) => ({ sourceId: source.result.sourceId,
      unitId: unit.id, disposition: "unresolved", factIds: [], duplicateOf: null }))) };
}

function response(value: unknown): Response {
  return new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });
}

test("generated fact sheet validates complete references", () => {
  const valid = sheet([entry]);
  assert.equal(validateFactSheet(valid), true);
  assert.equal(validateFactSheet({ ...valid, units: [{ ...valid.units[0], factIds: ["missing"] }] }), false);
});

test("manual assertion has user origin and survives a failed refresh", async () => {
  let calls = 0;
  const workflow = new FactWorkflow(() => {}, async () => {
    calls += 1;
    if (calls > 1) throw new Error("synthetic failure");
    return response(sheet([entry]));
  });
  const initial = [entry];
  workflow.sourcesChanged(initial);
  assert.equal(calls, 0);
  await workflow.update(initial);
  assert.equal(workflow.view.sheet?.units.length, entry.result.units.length);
  workflow.addAssertion("Led a synthetic team");
  const fact = workflow.view.sheet?.facts[0];
  assert.equal(fact?.origin, "user");
  assert.deepEqual(fact?.evidence, []);
  if (fact?.kind !== "text") throw new Error("missing assertion");
  const id = fact.id;
  workflow.editAssertion(id, "Built a synthetic team");
  assert.equal(workflow.view.sheet?.facts[0]?.id, id);
  assert.equal(workflow.view.sheet?.facts[0]?.revision, 2);
  workflow.sourcesChanged([{ ...entry, overlays: { "unit:unit_1": "Corrected" } }]);
  assert.equal(calls, 1);
  assert.equal(workflow.view.stale, true);
  assert.equal(workflow.view.sheet?.facts[0]?.id, id);
  assert.equal(entry.result.units[0]?.text, sourceFixture.units[0]?.text);
});

test("late response cannot replace a newer source revision", async () => {
  let resolveFirst: ((value: Response) => void) | undefined;
  const latest = { ...entry, overlays: { "unit:unit_1": "New correction" } };
  let calls = 0;
  const workflow = new FactWorkflow(() => {}, () => {
    calls += 1;
    if (calls === 1) return new Promise<Response>((resolve) => { resolveFirst = resolve; });
    return Promise.resolve(response(sheet([latest])));
  });
  const initial = [entry];
  const changed = [latest];
  workflow.sourcesChanged(initial);
  const pending = workflow.update(initial);
  workflow.sourcesChanged(changed);
  assert.equal(calls, 1);
  await workflow.update(changed);
  resolveFirst?.(response(sheet([entry])));
  await pending;
  assert.equal(workflow.view.stale, false);
  assert.equal(workflow.view.sheet?.units.length, latest.result.units.length);
  assert.equal(calls, 2);
});

test("cancelled fact refresh keeps accepted assertions and ignores its response", async () => {
  let resolvePending: ((value: Response) => void) | undefined;
  const workflow = new FactWorkflow(() => {}, () => new Promise<Response>((resolve) => { resolvePending = resolve; }));
  workflow.addAssertion("Verified synthetic result");
  const id = workflow.view.sheet?.facts[0]?.id;
  const initial = [entry];
  workflow.sourcesChanged(initial);
  const pending = workflow.update(initial);
  workflow.cancel();
  resolvePending?.(response(sheet([entry])));
  await pending;
  assert.equal(workflow.view.pending, false);
  assert.equal(workflow.view.sheet?.facts[0]?.id, id);
  assert.equal(workflow.view.sheet?.facts.length, 1);
});

test("correcting a source fact keeps its literal and links a user assertion", async () => {
  const sourceFact = { id: "fact_source", revision: 1, kind: "technology", value: { canonicalId: "python", display: "Python", scope: "global" },
    evidence: [{ sourceId: entry.result.sourceId, sourceRevision: 1, unitId: "unit_1", unitRevision: 1 }],
    origin: "source", importance: "normal", jobId: null, subprojectId: null };
  const basic = sheet([entry]);
  const reply = { ...basic, facts: [sourceFact], units: basic.units.map((unit, index) =>
    index === 0 ? { ...unit, factIds: [sourceFact.id] } : unit) };
  const workflow = new FactWorkflow(() => {}, async () => response(reply));
  await workflow.update([entry]);
  workflow.correctFact(sourceFact.id, "Python 3 only");
  assert.equal(workflow.view.sheet?.facts[0]?.id, sourceFact.id);
  assert.equal(workflow.view.sheet?.facts[0]?.origin, "source");
  const correctionId = workflow.view.sheet?.userCorrections?.[sourceFact.id];
  const correction = workflow.view.sheet?.facts.find((fact) => fact.id === correctionId);
  assert.equal(correction?.origin, "user");
  assert.deepEqual(correction?.evidence, []);
});
