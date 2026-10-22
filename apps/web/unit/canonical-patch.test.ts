import assert from "node:assert/strict";
import test from "node:test";
import { sha256 } from "../src/background/wire";
import { applyCanonicalPatch, applyVerifiedCanonicalPatch, type CanonicalPatchStep } from "../src/contracts/canonical-patch";
import { parseJsonWire } from "../src/contracts/lossless-json";

test("structural patches preserve Python number tokens, prototype keys and base bytes", async () => {
  const base = parseJsonWire('{"__proto__":{"a/~":"A😀B"},"integer":9007199254740993,"n":1e-07,"z":-0.0}');
  const expected = '{"__proto__":{"a/~":"A😎B"},"integer":9007199254740993,"n":1e-07,"new":1e+30,"z":-0.0}';
  const steps: CanonicalPatchStep[] = [
    { kind: "splice_text", pointer: "/__proto__/a~1~0", beforeTextHash: await sha256("A😀B"), start: 1, end: 3, text: "😎" },
    { kind: "set", pointer: "/new", valueWire: "1e+30" },
  ];
  const result = await applyVerifiedCanonicalPatch(base, steps, await sha256(base.wire), await sha256(expected));
  assert.equal(result.wire, expected);
  assert.ok(base.wire.includes("A😀B"));
  await assert.rejects(applyVerifiedCanonicalPatch(base, steps, "0".repeat(64), await sha256(expected)), /INVALID_RESULT/);
  await assert.rejects(applyVerifiedCanonicalPatch(base, steps, await sha256(base.wire), "0".repeat(64)), /INVALID_RESULT/);
});

test("nested edits, descending removals and ascending final inserts can reuse numeric pointers", async () => {
  const base = parseJsonWire('{"a":[{"id":"a","text":"old"},{"id":"b"},{"id":"c"}]}');
  const steps: CanonicalPatchStep[] = [
    { kind: "splice_text", pointer: "/a/1/id", beforeTextHash: await sha256("b"), start: 0, end: 1, text: "B" },
    { kind: "remove", pointer: "/a/2" }, { kind: "remove", pointer: "/a/0" },
    { kind: "insert", pointer: "/a/0", valueWire: '{"id":"new"}' },
    { kind: "insert", pointer: "/a/2", valueWire: '{"id":"tail"}' },
  ];
  assert.equal((await applyCanonicalPatch(base, steps)).wire, '{"a":[{"id":"new"},{"id":"B"},{"id":"tail"}]}');
});

test("a one-character delta excludes unchanged large data", async () => {
  const base = parseJsonWire(JSON.stringify({ a: { provenance: "P".repeat(1024 * 1024), text: "A".repeat(10000) }, sibling: "X".repeat(1024 * 1024) }));
  const steps: CanonicalPatchStep[] = [{ kind: "splice_text", pointer: "/a/text", beforeTextHash: await sha256("A".repeat(10000)), start: 1, end: 2, text: "😀" }];
  assert.ok(JSON.stringify(steps).length < 300);
  const result = await applyCanonicalPatch(base, steps);
  assert.equal(result.children.get("sibling")?.wire, base.children.get("sibling")?.wire);
  assert.ok(result.wire.includes("A😀A"));
});

test("invalid and overlapping patches reject without changing the retained base", async () => {
  const base = parseJsonWire('{"a":[{"x":0},{"x":0}],"text":"😀AB"}');
  const cases: CanonicalPatchStep[][] = [
    [{ kind: "set", pointer: "", valueWire: "{}" }],
    [{ kind: "set", pointer: "a", valueWire: "1" }],
    [{ kind: "set", pointer: "/a~2", valueWire: "1" }],
    [{ kind: "set", pointer: "/a/-", valueWire: "1" }],
    [{ kind: "set", pointer: "/a/01", valueWire: "1" }],
    [{ kind: "set", pointer: "/missing/child", valueWire: "1" }],
    [{ kind: "insert", pointer: "/a", valueWire: "1" }],
    [{ kind: "remove", pointer: "/missing" }],
    ...['{"x":1,"x":2}', '{ "x":1}', "NaN", "1e999", '"\\ud800"'].map(valueWire => [{ kind: "set" as const, pointer: "/a", valueWire }]),
    [{ kind: "set", pointer: "/a/0/x", valueWire: "1" }, { kind: "remove", pointer: "/a/0" }],
    [{ kind: "set", pointer: "/a", valueWire: "[]" }, { kind: "insert", pointer: "/a/0", valueWire: "1" }],
    [{ kind: "set", pointer: "/a/0/x", valueWire: "1" }, { kind: "set", pointer: "/a/0/x", valueWire: "2" }],
    [{ kind: "remove", pointer: "/a/0" }, { kind: "remove", pointer: "/a/0" }],
    [{ kind: "insert", pointer: "/a/0", valueWire: "{}" }, { kind: "set", pointer: "/a/0/x", valueWire: "1" }],
    [{ kind: "insert", pointer: "/a/0", valueWire: "1" }, { kind: "insert", pointer: "/a/0", valueWire: "2" }],
    [{ kind: "splice_text", pointer: "/text", beforeTextHash: await sha256("😀AB"), start: 1, end: 2, text: "x" }],
    [{ kind: "splice_text", pointer: "/text", beforeTextHash: "0".repeat(64), start: 0, end: 2, text: "x" }],
    [{ kind: "splice_text", pointer: "/text", beforeTextHash: await sha256("😀AB"), start: 0, end: 2, text: "\ud800" }],
  ];
  for (const steps of cases) await assert.rejects(applyCanonicalPatch(base, steps), /INVALID_RESULT/, JSON.stringify(steps));
  assert.equal(base.wire, '{"a":[{"x":0},{"x":0}],"text":"😀AB"}');
});
