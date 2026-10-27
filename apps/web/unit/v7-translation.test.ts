import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { containerKey, correctionRange, createdLocals, translateIntent, type LocalContainer, type V7Intent } from "../src/rich/v7-translation";

const response = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/projects/v7-response.json", import.meta.url), "utf8")) as TemplateProjectResponseV1;
const container: LocalContainer = { blockId: "block-paper-a", kind: "content", cellId: null };
const styles = { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" };
const intent: V7Intent = { localId: "op", prior: new Map([[containerKey(container), "By Shared title / Journal North."]]),
  operation: { kind: "replace_text", container, start: 8, end: 8, text: "X", styles, side: "interior" } };
const basis = { response, locals: new Map<string, string>() };

test("typing resolves the field from the last response without an address map", () => {
  const result = translateIntent(intent, basis);
  assert.ok(result.kind === "operation" && result.operation.kind === "replace_text");
  assert.deepEqual(result.operation.range.insertionTarget, { kind: "field", bindingId: "fragment-paper-a" });
});

test("changed text, missing containers and invalid ranges conflict", () => {
  assert.equal(translateIntent({ ...intent, prior: new Map([[containerKey(container), "different"]]) }, basis).kind, "conflict");
  assert.ok(intent.operation.kind === "replace_text");
  for (const patch of [{ start: 100, end: 100 }, { side: null }, { container: { ...container, blockId: "missing" } }]) {
    assert.equal(translateIntent({ ...intent, operation: { ...intent.operation, ...patch } }, basis).kind, "conflict");
  }
});

test("split output maps its local block only through its own createdBlocks entry", () => {
  const split: V7Intent = { ...intent, operation: { kind: "split_block", container, offset: 8, created: "local-right" } };
  assert.deepEqual(createdLocals(split, { op: ["canonical-right"] }), new Map([["local-right", "canonical-right"]]));
  assert.equal(createdLocals(split, { other: ["canonical-right"] }), null);
  assert.equal(createdLocals(split, { op: ["a", "b"] }), null);
});

test("correction ranges only bound the change and never split a surrogate pair", () => {
  assert.equal(correctionRange("same", "same"), null);
  assert.deepEqual(correctionRange("abc", "abXc"), { start: 2, end: 2, text: "X" });
  assert.deepEqual(correctionRange("aa", "aaa"), { start: 2, end: 2, text: "a" });
  assert.deepEqual(correctionRange("abc", ""), { start: 0, end: 3, text: "" });
  assert.deepEqual(correctionRange("a😀b", "a😃b"), { start: 1, end: 3, text: "😃" });
  assert.deepEqual(correctionRange("x😀", "x😀😀"), { start: 3, end: 3, text: "😀" });
  for (const [canonical, editor] of [["😀a", "😃a"], ["a😀", "a😃"], ["ab", "a😀b"], ["😀😀", "😀"]] as const) {
    const range = correctionRange(canonical, editor);
    assert.ok(range);
    const rebuilt = canonical.slice(0, range.start) + range.text + canonical.slice(range.end);
    assert.equal(rebuilt, editor);
    for (const point of [range.start, range.end]) {
      const left = canonical.charCodeAt(point - 1), right = canonical.charCodeAt(point);
      assert.ok(!(left >= 0xd800 && left <= 0xdbff && right >= 0xdc00 && right <= 0xdfff), `${canonical}->${editor}`);
    }
  }
});
