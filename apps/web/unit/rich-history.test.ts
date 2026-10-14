import assert from "node:assert/strict";
import test from "node:test";
import { SessionHistory, type CellChange, type DependencyCapture } from "../src/rich/history";

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
