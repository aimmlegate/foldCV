import assert from "node:assert/strict";
import test from "node:test";
import { literalRuns } from "../src/rich/v7-presentation";

test("literal style ranges ignore field keys and reversed bounds", () => {
  assert.deepEqual(literalRuns(undefined), []);
  assert.deepEqual(literalRuns({ "binding-1": "emphasis", "literal@0@4": "emphasis", "literal@4@4": "emphasis",
    "literal@x@2": "emphasis", "literal@8@6": "caption", "literal@2@3": "" }), [{ start: 0, end: 4, style: "emphasis" }]);
  assert.deepEqual(literalRuns({ "literal@10@12": "caption", "literal@1@2": "emphasis" }),
    [{ start: 1, end: 2, style: "emphasis" }, { start: 10, end: 12, style: "caption" }]);
});
