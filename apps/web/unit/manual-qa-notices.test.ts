import assert from "node:assert/strict";
import { test } from "node:test";
import { groupedWarnings, processingFailure, warningLabel } from "../src/workbench/import/notices";

test("equal warnings group while unknown codes and processing causes remain useful", () => {
  const grouped = groupedWarnings([...Array<string>(7).fill("IMAGE"), "UNKNOWN_GAP"]);
  assert.equal(grouped.length, 2);
  assert.match(grouped[0] ?? "", /Повторов: 7/u);
  assert.match(grouped[1] ?? "", /UNKNOWN_GAP/u);
  assert.match(warningLabel("NO_TEXT"), /скана/u);
  assert.match(processingFailure({ id: "g", status: "failed", stage: "normalize_semantics", errorCode: "INPUT_TOO_LARGE" }) ?? "", /Извлечение фактов:.*INPUT_TOO_LARGE/u);
  assert.equal(processingFailure({ id: "g", status: "completed", stage: "render", errorCode: null }), null);
});
