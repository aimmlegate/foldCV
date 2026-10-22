import assert from "node:assert/strict";
import test from "node:test";
import { SessionHistory, type CellChange, type DependencyCapture } from "../src/rich/history";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { factCells, factsFromCells, factFieldCell } from "../src/rich/fact-cells";
import { documentCells, type StoredBlock } from "../src/rich/document-cells";
import { historyMutation } from "../src/rich/history-offer";

test("effects receive their actual action and reconciliation origin before publication", () => {
  const effects: { actionId: string | null; token: number | undefined; kind: string }[] = [];
  const h = new SessionHistory("session", new Map([["first", "A"], ["other", "B"]]), (_changes, context) => {
    effects.push({ actionId: context.actionId, token: context.actionToken, kind: context.kind });
  });
  const first = h.commit("typing", [{ key: "first", before: "A", after: "AA" }], "group");
  assert.ok(first);
  assert.equal(h.commit("typing", [{ key: "first", before: "AA", after: "AAA" }], "group"), first);
  const capture = h.capture(first, ["first"]); assert.ok(capture);
  const second = h.commit("panel", [{ key: "other", before: "B", after: "BB" }]); assert.ok(second);
  assert.equal(h.attach(capture, [{ key: "first", before: "AAA", after: "Reconciled" }]), "applied");
  assert.deepEqual(effects, [
    { actionId: first, token: 0, kind: "typing" }, { actionId: first, token: 1, kind: "typing" },
    { actionId: second, token: 0, kind: "panel" }, { actionId: first, token: 2, kind: "reconciliation" },
  ]);
  assert.equal(h.currentActionId, second);
});

test("a net-empty typing group leaves no Undo barrier or reusable delayed capture", () => {
  const h = history();
  const first = h.commit("typing", [edit(h, "block:other", "Changed")], "same-group"); assert.ok(first);
  const pending = capture(h, first, ["block:other"]);
  assert.equal(h.commit("typing", [edit(h, "block:other", "Other job")], "same-group"), null);
  assert.equal(h.position, 0);
  assert.equal(h.length, 0);
  assert.equal(h.navigation("undo"), null);
  assert.equal(h.current(pending), false);
  const next = h.commit("typing", [edit(h, "block:other", "Continued")], "same-group"); assert.ok(next);
  assert.notEqual(next, first);
  assert.equal(h.attach(pending, [edit(h, "block:other", "Late response")]), "stale");
  assert.equal(h.undo(), true);
  assert.equal(h.read("block:other"), "Other job");
});

test("prepared Undo and Redo use the same history cursor and preserve request cancellation", () => {
  const h = history();
  h.commit("typing", [edit(h, "block:other", "Edited"), { key: "request:pending", before: null, after: "pending" }]);
  const offered = h.navigation("undo");
  assert.ok(offered);
  assert.equal(h.position, 1);
  const saved = offered.changes.filter(change => !change.key.startsWith("request:"));
  const reservation = h.reserve("native-undo");
  assert.ok(reservation);
  assert.equal(h.publishNavigation(reservation, "undo", [{ ...saved[0]!, after: "Foreign" }]), false);
  assert.equal(h.position, 1);
  assert.equal(h.publishNavigation(reservation, "undo", saved), true);
  assert.equal(h.position, 0);
  assert.equal(h.length, 1);
  assert.equal(h.read("request:pending"), null);
  const redo = h.navigation("redo"), next = h.reserve("native-redo");
  assert.ok(redo && next);
  assert.equal(h.publishNavigation(next, "redo", redo.changes.filter(change => !change.key.startsWith("request:"))), true);
  assert.equal(h.position, 1);
  assert.equal(h.length, 1);
  assert.equal(h.read("block:other"), "Edited");
});

test("history offers reuse the mutation compiler and fact cells retain extraction diagnostics", () => {
  const value: unknown = structuredClone(fixture);
  assert.ok(validateRichWorkspaceShape(value) && value.project);
  const project = value.project;
  project.facts.extraction = { status: "partial", factCount: project.facts.records.length,
    counts: { candidate: 1 }, requestBytes: 80000, recoveredRows: 0, unresolved: [] };
  const cache = new Map<string, StoredBlock>(), current = new Map([...documentCells(project.document, cache), ...factCells(project.facts)]);
  const h = new SessionHistory("editor-owner", current), candidate = project.facts.records.find(record => record.kind === "candidate");
  assert.ok(candidate);
  const key = factFieldCell(candidate.id, "name"), before = h.read(key);
  assert.ok(before);
  const changed = JSON.stringify({ ...candidate.name, rawText: "Changed by user", value: "Changed by user" });
  h.commit("panel", [{ key, before, after: changed }]);
  const cells = new Map(current);cells.set(key, changed);
  const edited = { ...project, facts: factsFromCells(cells, project.facts) };
  assert.deepEqual(edited.facts.extraction, project.facts.extraction);
  const undo = h.navigation("undo");assert.ok(undo);
  const request = historyMutation(edited, h.session, "undo", undo.changes, cells, cache);
  assert.ok(request);
  assert.equal(request.kind, "undo");
  assert.equal(request.capture.sessionId, h.session);
  const restored = request.steps.find(step => step.kind === "put_record");assert.ok(restored?.kind === "put_record");
  assert.equal(restored.record.kind, "candidate");
  if (restored.record.kind === "candidate") assert.equal(restored.record.name.rawText, candidate.name.rawText);
});

function history() { return new SessionHistory("session-1", new Map([
  ["block:name", "Alex"], ["fact:name", "Alex"], ["block:narrative", "Alex leads"],
  ["block:other", "Other job"], ["fact:period", "Jan-Apr"], ["owner:narrative", "job-1"],
])); }
function edit(h: SessionHistory, key: string, after: string | null): CellChange { return { key, before: h.read(key), after }; }
function capture(h: SessionHistory, id: string | null, keys: string[]): DependencyCapture {
  assert.ok(id);
  const value = h.capture(id, keys);
  assert.ok(value);
  return value;
}

test("rich history orders typing, panel, rewrite and cascade in one cursor", () => {
  const h = history();
  h.commit("typing", [edit(h, "block:other", "Typed")], "typing-1");
  h.commit("typing", [edit(h, "block:other", "Typed more")], "typing-1");
  h.commit("panel", [edit(h, "fact:name", "Sam"), edit(h, "block:name", "Sam")]);
  h.commit("rewrite", [edit(h, "block:narrative", "Sam leads well")]);
  h.commit("cascade", [edit(h, "fact:period", "May-Jul"), edit(h, "block:period", "May-Jul")]);
  assert.equal(h.length, 4);
  for (let i = 0; i < 4; i++) assert.equal(h.undo(), true);
  assert.equal(h.read("block:other"), "Other job");
  assert.equal(h.read("fact:name"), "Alex");
  assert.equal(h.read("block:period"), null);
  const revision = h.revisionClock;
  for (let i = 0; i < 4; i++) assert.equal(h.redo(), true);
  assert.ok(h.revisionClock > revision);
  assert.equal(h.read("fact:period"), "May-Jul");
  assert.equal(h.read("block:name"), h.read("fact:name"));
});

test("rich delayed reconciliation joins its origin and preserves unrelated typing", () => {
  const h = history();
  const id = h.commit("panel", [edit(h, "fact:name", "Sam"), edit(h, "block:name", "Sam")]);
  const ticket = capture(h, id, ["fact:name", "block:narrative", "owner:narrative"]);
  h.commit("typing", [edit(h, "block:other", "Independent typing")]);
  assert.equal(h.attach(ticket, [edit(h, "block:narrative", "Sam leads")]), "applied");
  assert.equal(h.length, 2);
  assert.equal(h.undo(), true);
  assert.equal(h.read("block:narrative"), "Sam leads");
  assert.equal(h.undo(), true);
  assert.equal(h.read("block:narrative"), "Alex leads");
  assert.equal(h.read("fact:name"), "Alex");
  assert.equal(h.redo(), true);
  assert.equal(h.read("block:narrative"), "Sam leads");
});

test("rich dependency epochs reject undo redo deletion and equal-text replacement", () => {
  for (const mutate of [
    (h: SessionHistory) => { h.undo(); h.redo(); },
    (h: SessionHistory) => { h.commit("structure", [edit(h, "block:narrative", null)]); },
    (h: SessionHistory) => { h.commit("typing", [edit(h, "block:narrative", "Changed")]); h.commit("typing", [edit(h, "block:narrative", "Alex leads")]); },
    (h: SessionHistory) => { h.commit("structure", [edit(h, "owner:narrative", "job-2")]); },
  ]) {
    const h = history();
    const id = h.commit("panel", [edit(h, "fact:name", "Sam")]);
    const ticket = capture(h, id, ["fact:name", "block:narrative", "owner:narrative"]);
    mutate(h);
    assert.equal(h.attach(ticket, [edit(h, "block:narrative", "Sam leads")]), "stale");
  }
});

test("rich unsafe inverse and uncaptured writes keep the accepted state", () => {
  const h = history();
  const id = h.commit("panel", [edit(h, "fact:name", "Sam")]);
  const ticket = capture(h, id, ["fact:name", "block:narrative"]);
  assert.equal(h.attach(ticket, [edit(h, "block:other", "Unexpected")]), "conflict");
  assert.equal(h.attach(ticket, [{ key: "block:narrative", before: "Wrong", after: "New" }]), "conflict");
  assert.equal(h.read("block:other"), "Other job");
  assert.equal(h.read("block:narrative"), "Alex leads");
  assert.equal(h.length, 1);
  assert.equal(h.commit("panel", [edit(h, "fact:name", "Wrong"), edit(h, "fact:name", "Duplicate")]), null);
  h.close();
  assert.equal(h.attach(ticket, [edit(h, "block:narrative", "Sam leads")]), "stale");
});

test("rich composition is one action and a new action removes the redo branch", () => {
  const h = history();
  h.commit("composition", [edit(h, "block:name", "А")], "ime-1");
  h.commit("composition", [edit(h, "block:name", "Алекс")], "ime-1");
  assert.equal(h.length, 1);
  h.undo();
  assert.equal(h.read("block:name"), "Alex");
  h.commit("panel", [edit(h, "fact:name", "New")]);
  assert.equal(h.redo(), false);
  assert.equal(h.length, 1);
});

test("rich retry cannot recapture newer dependencies for an older action", () => {
  const h = history();
  const id = h.commit("panel", [edit(h, "fact:name", "Sam")]);
  assert.ok(id);
  h.commit("typing", [edit(h, "block:other", "Independent")]);
  assert.ok(h.capture(id, ["fact:name", "block:narrative"]));
  h.commit("panel", [edit(h, "fact:name", "New name")]);
  assert.equal(h.capture(id, ["fact:name", "block:narrative"]), null);
  assert.equal(h.read("fact:name"), "New name");
});
