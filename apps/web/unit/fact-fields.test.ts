import assert from "node:assert/strict";
import test from "node:test";
import { needsCheck } from "../src/rich/fact-fields";

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
