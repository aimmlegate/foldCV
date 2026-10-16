import assert from "node:assert/strict";
import test from "node:test";
import { SessionHistory } from "../src/rich/history";
import type { CapturedEditorSelection } from "../src/rich/Editor";
import { capturedSelectionCurrent } from "../src/workbench/editor/capture";

test("rewrite opened before typing rejects the changed target even after Undo returns equal text", () => {
  const history = new SessionHistory("editor-1", new Map([["block:a", "original"], ["block:b", "other"]]));
  const capture: CapturedEditorSelection = { session: "editor-1", epochs: new Map([["block:a", history.revision("block:a")]]),
    selection: { kind: "text", blockIds: ["a"], anchor: { blockId: "a", cellId: null, offset: 0 }, head: { blockId: "a", cellId: null, offset: 8 } } };
  history.commit("typing", [{ key: "block:b", before: "other", after: "independent" }]);
  assert.equal(capturedSelectionCurrent(capture, history, "editor-1"), true);
  history.commit("typing", [{ key: "block:a", before: "original", after: "changed" }]);
  assert.equal(capturedSelectionCurrent(capture, history, "editor-1"), false);
  history.undo(); assert.equal(history.read("block:a"), "original");
  assert.equal(capturedSelectionCurrent(capture, history, "editor-1"), false);
  assert.equal(capturedSelectionCurrent(capture, history, "editor-2"), false);
});

test("failed request cleanup removes only its empty marker and preserves later edits and Undo", () => {
  const history = new SessionHistory("editor-1", new Map([["block:a", "original"]]));
  const pending = history.commit("rewrite", [{ key: "request:1", before: null, after: "pending" }]); assert.ok(pending);
  history.commit("typing", [{ key: "block:a", before: "original", after: "later" }]);
  assert.equal(history.discardPending(pending), true);
  assert.equal(history.length, 1); assert.equal(history.position, 1); assert.equal(history.read("block:a"), "later");
  assert.equal(history.undo(), true); assert.equal(history.read("block:a"), "original");
  assert.equal(history.redo(), true); assert.equal(history.read("block:a"), "later");
  const real = history.currentActionId; assert.ok(real); assert.equal(history.discardPending(real), false);
});
