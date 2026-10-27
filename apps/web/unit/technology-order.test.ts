import test from "node:test";
import assert from "node:assert/strict";
import { adjacentTechnology, documentTechnologies } from "../src/rich/technology-order";
import { facts, technology } from "./support/facts";

test("keyboard moves work at both edges and can place an item last", () => {
  assert.equal(adjacentTechnology(["a", "b", "c"], "a", -1), undefined);
  assert.equal(adjacentTechnology(["a", "b", "c"], "a", 1), "c");
  assert.equal(adjacentTechnology(["a", "b", "c"], "b", 1), null);
  assert.equal(adjacentTechnology(["a", "b", "c"], "c", 1), undefined);
  assert.equal(adjacentTechnology(["a", "b", "c"], "c", -1), "b");
  assert.equal(adjacentTechnology(["a", "b", "c"], "removed", 1), undefined);
});

test("facts follow authored main text order while Focus stays separate", () => {
  const value = facts(["SQL", "Python", "Docker"].map((display, index) => technology(`tool-${index}`, display)));
  const span = (index: number) => ({ type: "fact_field", bindingId: `binding-${index}`, fieldKey: "display", recordId: `tool-${index}`, text: "tool" });
  const paragraph = { id: "ordered-tools", type: "paragraph", props: {}, children: [], content: [2, 0, 1].map(span) };
  // A Focus list read first would give Python, SQL, Docker.
  const focus = { id: "focus", type: "section", props: { presentation: "focus" }, children: [{ ...paragraph, id: "focus-tools", content: [1, 0, 2].map(span) }] };
  const document = { regions: [{ role: "main", blocks: [focus, paragraph] }] };
  assert.deepEqual(documentTechnologies(value, document, null).map(record => record.display.rawText), ["Docker", "SQL", "Python"]);
  assert.deepEqual(value.records.filter(record => record.kind === "technology").map(record => record.display.rawText), ["SQL", "Python", "Docker"]);
});
