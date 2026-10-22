import assert from "node:assert/strict";
import test from "node:test";
import { WorkspaceReads } from "../src/workbench/read-capture";

function open(reads: WorkspaceReads, project: string) {
  const capture = reads.beginSelection(project);
  assert.ok(reads.adoptSelection(capture)); return capture;
}

test("A to B to A rejects the old editor opening despite equal project ID", () => {
  const reads = new WorkspaceReads(), old = open(reads, "A");
  open(reads, "B"); const latest = open(reads, "A");
  assert.equal(reads.matchesOpening(old), false);
  assert.ok(reads.matchesOpening(latest));
  assert.ok(latest.selectionEpoch > old.selectionEpoch);
  assert.ok(latest.requestId > old.requestId);
});

test("two same-project loads finishing backward cannot replace the latest opening", () => {
  const reads = new WorkspaceReads();
  const first = reads.beginSelection("A"), second = reads.beginSelection("A");
  assert.equal(reads.selectionCurrent(first), false);
  assert.ok(reads.adoptSelection(second));
  assert.equal(reads.adoptSelection(first), false);
  assert.deepEqual(reads.opening, second);
});

test("polling and exports have independent request slots and reject their older replies", () => {
  const reads = new WorkspaceReads(); open(reads, "A");
  const exported = reads.begin("export"), old = reads.begin("poll"), current = reads.begin("poll");
  assert.ok(exported && old && current);
  assert.equal(reads.current("poll", old), false);
  assert.ok(reads.current("poll", current));
  assert.ok(reads.current("export", exported));
  assert.equal(reads.current("archive", exported), false);
});

test("closing suppresses a pending download and polling without rewinding selection identity", () => {
  const reads = new WorkspaceReads(), opening = open(reads, "A");
  const exported = reads.begin("export"), poll = reads.begin("poll"); assert.ok(exported && poll);
  reads.clear();
  assert.equal(reads.current("export", exported), false);
  assert.equal(reads.current("poll", poll), false);
  assert.equal(reads.matchesOpening(opening), false);
  const reopened = open(reads, "A"); assert.ok(reopened.selectionEpoch > opening.selectionEpoch);
});

test("a failed load keeps the shown opening but never revives its old operation slots", () => {
  const reads = new WorkspaceReads(), opening = open(reads, "A");
  const poll = reads.begin("poll"); assert.ok(poll);
  const failed = reads.beginSelection("B");
  assert.equal(reads.begin("export"), null);
  assert.equal(reads.current("poll", poll), false);
  reads.cancelSelection(failed);
  assert.ok(reads.matchesOpening(opening));
  assert.equal(reads.current("poll", poll), false);
  assert.ok(reads.begin("poll"));
});

test("caller mutations cannot replace the owner's opening or request capture", () => {
  const reads = new WorkspaceReads(), opening = open(reads, "A");
  Reflect.set(opening, "projectId", "B");
  assert.equal(reads.opening?.projectId, "A");
  const exported = reads.begin("export"); assert.ok(exported);
  const captured = { ...exported }; Reflect.set(exported, "requestId", exported.requestId + 1);
  assert.ok(reads.current("export", captured));
  assert.equal(reads.current("export", exported), false);
});

test("failed archive replacement preserves the shown editor opening without reviving old operations", () => {
  const reads = new WorkspaceReads(), opening = open(reads, "A"), exported = reads.begin("export");
  assert.ok(exported);
  const version = reads.beginReplacement();
  assert.ok(reads.replacementCurrent(version));
  assert.equal(reads.current("export", exported), false);
  assert.equal(reads.begin("poll"), null);
  reads.cancelReplacement(version);
  assert.ok(reads.matchesOpening(opening));
  assert.equal(reads.current("export", exported), false);
  const newer = reads.beginReplacement(); reads.clear();
  assert.equal(reads.replacementCurrent(newer), false);
  assert.equal(reads.matchesOpening(opening), false);
});
