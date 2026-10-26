import assert from "node:assert/strict";
import test from "node:test";
import { parseCheck, parseConfigState, pointerRange, technicalLines } from "../src/workbench/settings/template/config";

const source = [
  "# yaml-language-server: $schema=schema.json",
  "schema_version: 3",
  "template:",
  "  id: generic",
  "  revision: 2.0.0",
  "assets:",
  "- id: logo",
  "  path: assets/logo.png",
  "- id: \"a/b\"",
  "  path: assets/a~b.png",
  "blocks:",
  "  - id: summary",
  "    view:",
  "      nodes: []",
  "",
].join("\n");
const marked = (pointer: string) => { const range = pointerRange(source, pointer); return source.slice(range.start, range.end); };

test("a server pointer marks the deepest key or value that exists", () => {
  assert.equal(marked("/template/revision"), "revision: 2.0.0");
  assert.equal(marked("/assets/1/path"), "path: assets/a~b.png");
  assert.equal(marked("/blocks/0/view/nodes"), "nodes");
  // A missing child (a required field) marks its parent key; a missing item marks the list's key.
  assert.equal(marked("/template/name"), "template");
  assert.equal(marked("/assets/7/path"), "assets");
  assert.equal(marked("/blocks/0"), "id: summary");
});

test("escaped pointer tokens and unknown roots fall back sensibly", () => {
  const escaped = "items:\n  a/b:\n    c~d: 1\n";
  const range = pointerRange(escaped, "/items/a~1b/c~0d");
  assert.equal(escaped.slice(range.start, range.end), "c~d: 1");
  // Root errors (syntax, wrong top type) mark the first content line, skipping comments.
  assert.equal(marked("/"), "schema_version: 3");
  assert.equal(marked("/nothing/here"), "schema_version: 3");
  const broken = "template: [\n";
  const root = pointerRange(broken, "/template/id");
  assert.ok(root.end > root.start && root.end <= broken.length);
  const empty = pointerRange("", "/");
  assert.deepEqual(empty, { start: 0, end: 1 });
});

test("responses are validated before use", () => {
  const summary = { id: "generic", name: "Generic", revision: "2.0.0", packageHash: "a".repeat(64) };
  assert.deepEqual(parseConfigState({ schemaVersion: 1, package: summary, format: "yaml", text: "x: 1\n", bundled: true }),
    { package: summary, format: "yaml", text: "x: 1\n", bundled: true });
  assert.throws(() => parseConfigState({ schemaVersion: 1, package: summary, format: "toml", text: "", bundled: true }), /INVALID_RESULT/);
  assert.throws(() => parseConfigState({ schemaVersion: 2, package: summary, format: "yaml", text: "", bundled: true }), /INVALID_RESULT/);
  assert.deepEqual(parseCheck({ schemaVersion: 1, valid: true, package: summary, error: null }), { valid: true, package: summary });
  assert.deepEqual(parseCheck({ schemaVersion: 1, valid: false, package: null, error: { path: "/template", message: "bad" } }),
    { valid: false, error: { path: "/template", message: "bad" } });
  assert.throws(() => parseCheck({ schemaVersion: 1, valid: false, package: null, error: null }), /INVALID_RESULT/);
  assert.throws(() => parseCheck({ schemaVersion: 1, valid: "yes" }), /INVALID_RESULT/);
});

test("technical sections are found by their top-level keys only", () => {
  const text = ["schema_version: 4", "template:", "  id: generic", "blocks:", "- id: projects", "  assets: nested", "style:",
    "  page: {}", "fact_types:", "- id: identity", "assets:", "  logo: assets/logo.png", "provenance: {}", ""].join("\n");
  assert.deepEqual(technicalLines(text), [6, 8, 10, 12]);
});
