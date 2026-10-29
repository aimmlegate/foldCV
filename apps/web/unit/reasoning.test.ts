import assert from "node:assert/strict";
import test from "node:test";
import { isReasoningEffort, longReasoning } from "../src/connection/reasoning";

test("high and the levels above it are the long ones; medium and below are not", () => {
  assert.deepEqual(["none", "minimal", "low", "medium"].map(value => isReasoningEffort(value) && longReasoning(value)),
    [false, false, false, false]);
  assert.deepEqual(["high", "xhigh", "max", "ultra"].map(value => isReasoningEffort(value) && longReasoning(value)),
    [true, true, true, true]);
});
