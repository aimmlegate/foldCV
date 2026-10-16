import assert from "node:assert/strict";
import test from "node:test";
import { sourceText } from "../src/workbench/editor/source";

test("plain source view keeps line endings and empty lines instead of adding paragraph gaps", () => {
  const input = { parser: "utf8", units: [{ order: 2, text: "Last" }, { order: 0, text: "First\r\n" }, { order: 1, text: "\r\n" }] };
  assert.equal(sourceText(input), "First\r\n\r\nLast");
  assert.deepEqual(input.units.map(unit => unit.order), [2, 0, 1]);
});
