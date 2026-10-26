import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { sha256 } from "../src/background/wire";
import { jsonWireAt, parseJsonWire } from "../src/contracts/lossless-json";

test("Python canonical bytes retain floats, exponents, negative zero, Unicode key order and escapes", async () => {
  const rows: unknown = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/canonical-json.json", import.meta.url), "utf8"));
  assert.ok(Array.isArray(rows));
  for (const row of rows as unknown[]) {
    assert.ok(typeof row === "object" && row !== null && "wire" in row && "sha256" in row
      && typeof row.wire === "string" && typeof row.sha256 === "string");
    const root = parseJsonWire(row.wire);
    assert.equal(root.wire, row.wire);
    assert.equal(await sha256(root.wire), row.sha256);
    assert.deepEqual(root.value, JSON.parse(row.wire));
  }
});

test("subtree selection keeps exact numeric spellings and safely handles prototype keys", () => {
  const root = parseJsonWire(' { "z":1.0, "a":{"__proto__":{"x":-0.0},"items":[1e-07,"\\u0061"]}} ');
  assert.equal(root.wire, '{"a":{"__proto__":{"x":-0.0},"items":[1e-07,"a"]},"z":1.0}');
  assert.equal(jsonWireAt(root, ["a", "items", 0]).wire, "1e-07");
  assert.ok(Object.is(jsonWireAt(root, ["a", "__proto__", "x"]).value, -0));
  assert.throws(() => jsonWireAt(root, ["a", "items", "0"]));
  assert.throws(() => jsonWireAt(root, ["missing"]));
});

test("ambiguous keys, malformed JSON, nonfinite numbers and broken Unicode cannot supply hash evidence", () => {
  for (const wire of ['{"a":1,"\\u0061":2}', '{"nested":{"x":1,"x":2}}', '[1,]', '{"x":}',
    '01', '-01', '1.', '1e', '1e999', 'true false', '"\\ud800"', '"\\udc00"', '"raw\nline"', '']) {
    assert.throws(() => parseJsonWire(wire), /INVALID_RESULT/, wire);
  }
});

test("a workspace wire of many megabytes nested as one string parses", () => {
  // A writer reply carries the whole workspace, fonts included, as one escaped string; the old regex overflowed.
  const workspace = JSON.stringify({ blocks: Array.from({ length: 280_000 }, (_, index) => ({ id: `b${index}`, text: 'a "quoted" \\ line\n' })) });
  const source = JSON.stringify({ workspaceWire: workspace, n: 1.50 }).replace('"n":1.5', '"n":1.50');
  assert.ok(workspace.length > 11_000_000);
  const root = parseJsonWire(source);
  assert.equal((root.value as { workspaceWire: string }).workspaceWire, workspace);
  assert.equal(root.children.get("workspaceWire")?.wire, JSON.stringify(workspace));
  assert.equal(root.children.get("n")?.wire, "1.50");
});

test("escapes decode like JSON.parse and the wire is canonical", () => {
  const source = String.raw`{"b":"\u0041\/\b\f\n\r\t\"\\ \ud83d\ude00 é","a":[]}`;
  const root = parseJsonWire(source);
  assert.deepEqual(root.value, JSON.parse(source));
  assert.equal(root.wire, `{"a":[],"b":${JSON.stringify((JSON.parse(source) as { b: string }).b)}}`);
  assert.equal(parseJsonWire('""').value, "");
});

test("malformed or unsafe strings are refused", () => {
  for (const source of ['"open', '"\\x"', '"\\u12"', '"\\u12G4"', '"\\', '"a\u0001b"', '"\\ud800"', '"\\udc00x"', '{"a":"\\ud83d"}', "'a'"]) {
    assert.throws(() => parseJsonWire(source), /INVALID_RESULT/, source);
  }
});
