import assert from "node:assert/strict";
import test from "node:test";
import { notificationTotal, updateNotificationCounts } from "../src/workbench/ui/notification-counts";

test("source, editor, error and job notices share a count without clearing each other", () => {
  let counts: ReadonlyMap<string, number> = new Map();
  for (const [id, count] of [["source", 3], ["editor", 2], ["error", 1], ["jobs", 2]] as const)
    counts = updateNotificationCounts(counts, id, count);
  assert.equal(notificationTotal(counts), 8);
  counts = updateNotificationCounts(counts, "error", 0);
  counts = updateNotificationCounts(counts, "jobs", 1);
  assert.equal(notificationTotal(counts), 6);
  assert.equal(counts.get("source"), 3);
  assert.equal(counts.get("editor"), 2);
});

test("switching project removes old editor notices without losing new recovery or global messages", () => {
  let counts: ReadonlyMap<string, number> = new Map([["old-editor", 2], ["jobs", 1]]);
  counts = updateNotificationCounts(counts, "new-editor", 1);
  counts = updateNotificationCounts(counts, "old-editor", 0);
  assert.equal(notificationTotal(counts), 2);
  assert.deepEqual([...counts.keys()], ["jobs", "new-editor"]);
  assert.equal(updateNotificationCounts(counts, "old-editor", 0), counts);
  assert.equal(updateNotificationCounts(counts, "new-editor", 1), counts);
});
