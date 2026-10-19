import assert from "node:assert/strict";
import test from "node:test";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import { editorNoticeState } from "../src/workbench/editor/notices";

type SyncRecord = RichProjectResponse["workspace"]["syncRecords"][number];
const sync = (id: string, status: SyncRecord["status"], errorCode: string | null): SyncRecord => ({
  id, status, errorCode, actionId: id, blockIds: [], factIds: [], fieldKeys: [], dependencies: [],
});

test("recovery and warnings remain counted independently of sync dismissal", () => {
  const state = editorNoticeState("read_only", "OUTCOME_UNKNOWN", [sync("dismissal", "stale", "USER_DISMISSED")]);
  assert.equal(state.recovery, true);
  assert.equal(state.count, 2);
  assert.deepEqual(state.records, []);
});

test("dismissed sync records stay hidden after reload while new and actionable records remain", () => {
  const syncRecords = [sync("old-dismissal", "stale", null), sync("dismissal", "stale", "USER_DISMISSED"),
    sync("outdated", "stale", "STALE_SYNC"), sync("new-failure", "failed", "MODEL_FAILED"), sync("done", "applied", null)];
  const state = editorNoticeState(null, "", syncRecords);
  assert.equal(state.count, 2);
  assert.deepEqual(state.records.map(record => record.id), ["outdated", "new-failure"]);
  assert.equal(editorNoticeState(null, "", syncRecords.slice(0, 2)).count, 0);
});

test("a new result for a previously dismissed action returns to the notice list", () => {
  const before = sync("retry", "stale", "USER_DISMISSED");
  assert.equal(editorNoticeState("normal", "", [before]).count, 0);
  const after = { ...before, status: "failed" as const, errorCode: "MODEL_FAILED" };
  assert.equal(editorNoticeState("normal", "", [after]).count, 1);
});

test("an expected rewrite preview does not create a second sync notification", () => {
  const ready = { ...sync("preview", "pending", null), kind: "rewrite" as const, ready: true, rewriteResult: "New text" };
  assert.equal(editorNoticeState("normal", "", [ready]).count, 0);
  assert.equal(editorNoticeState("normal", "", [{ ...ready, status: "failed", errorCode: "MODEL_FAILED" }]).count, 1);
});
