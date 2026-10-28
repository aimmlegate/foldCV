import assert from "node:assert/strict";
import test from "node:test";
import type { ProjectListEntry } from "../src/projects/api";
import { historyGroups } from "../src/workbench/layout/history-groups";

const entry = (projectId: string, options: Partial<ProjectListEntry> = {}): ProjectListEntry => ({
  projectId, title: projectId, updatedAt: "2026-10-01T10:00:00+00:00", tombstoned: false, cleanupStatus: "none", ...options,
});
const ids = (entries: readonly ProjectListEntry[]) => entries.map(item => item.projectId);

test("the sidebar keeps the listing order and never lifts a recently opened or edited resume", () => {
  const listing = [entry("newest"), entry("middle", { lastOpenedAt: "2026-10-28T09:00:00+00:00", updatedAt: "2026-10-28T09:00:00+00:00" }),
    entry("oldest", { lastOpenedAt: "2026-10-27T09:00:00+00:00" })];
  const groups = historyGroups(listing);
  assert.deepEqual(ids(groups.current), ["newest", "middle", "oldest"]);
  assert.deepEqual(groups.archived, []);
});

test("archived resumes move to their own list in the same order and leave the main list", () => {
  const groups = historyGroups([entry("e", { archived: true }), entry("d"), entry("c", { archived: true }), entry("b", { archived: false }), entry("a", { archived: true })]);
  assert.deepEqual(ids(groups.current), ["d", "b"]);
  assert.deepEqual(ids(groups.archived), ["e", "c", "a"]);
});

test("an entry without the archive flag counts as in use", () => {
  assert.deepEqual(ids(historyGroups([entry("plain")]).current), ["plain"]);
  assert.deepEqual(historyGroups([]), { current: [], archived: [] });
});
