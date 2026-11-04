import assert from "node:assert/strict";
import test from "node:test";
import { parseCheck, parseConfigState, parseSave, pointerRange, technicalLines, withState } from "../src/workbench/templates/config";

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
  assert.deepEqual(parseConfigState({ schemaVersion: 1, package: summary, format: "yaml", text: "x: 1\n", bundled: true, edited: false }),
    { package: summary, format: "yaml", text: "x: 1\n", bundled: true, edited: false });
  assert.throws(() => parseConfigState({ schemaVersion: 1, package: summary, format: "toml", text: "", bundled: true, edited: false }), /INVALID_RESULT/);
  assert.throws(() => parseConfigState({ schemaVersion: 2, package: summary, format: "yaml", text: "", bundled: true, edited: false }), /INVALID_RESULT/);
  assert.throws(() => parseConfigState({ schemaVersion: 1, package: summary, format: "yaml", text: "", bundled: true }), /INVALID_RESULT/);
  assert.deepEqual(parseCheck({ schemaVersion: 1, valid: true, package: summary, error: null }), { valid: true, package: summary });
  assert.deepEqual(parseCheck({ schemaVersion: 1, valid: false, package: null, error: { path: "/template", message: "bad" } }),
    { valid: false, error: { path: "/template", message: "bad" } });
  assert.throws(() => parseCheck({ schemaVersion: 1, valid: false, package: null, error: null }), /INVALID_RESULT/);
  assert.throws(() => parseCheck({ schemaVersion: 1, valid: "yes" }), /INVALID_RESULT/);
});

test("a save or reset updates only its own template in the list and keeps the default", () => {
  const entry = (id: string, revision: string, edited: boolean) => ({ id, name: id, revision, packageHash: id.padEnd(64, "0"), bundled: true, edited });
  const catalog = { defaultId: "second", templates: [entry("generic", "2.6.0", false), entry("second", "1.0.0", false)] };
  const saved = { package: { id: "generic", name: "Generic edited", revision: "9.0.0", packageHash: "b".repeat(64) }, format: "yaml" as const,
    text: "", bundled: true, edited: true };
  assert.deepEqual(withState(catalog, saved), { defaultId: "second", templates: [
    { id: "generic", name: "Generic edited", revision: "9.0.0", packageHash: "b".repeat(64), bundled: true, edited: true }, catalog.templates[1]] });
  // A created template joins the list as the server lists it: after the shipped ones, own templates by id.
  const own = { package: { id: "custom-moy", name: "Мой", revision: "1.0.0", packageHash: "c".repeat(64) }, format: "yaml" as const, text: "", bundled: false, edited: true };
  const created = withState(catalog, own);
  assert.deepEqual(created.templates.map(entry => entry.id), [...catalog.templates.map(entry => entry.id), "custom-moy"]);
  const earlier = withState(created, { ...own, package: { ...own.package, id: "custom-a" } });
  assert.deepEqual(earlier.templates.map(entry => entry.id), [...catalog.templates.map(entry => entry.id), "custom-a", "custom-moy"]);
});

test("technical sections are found by their top-level keys only", () => {
  const text = ["schema_version: 4", "template:", "  id: generic", "blocks:", "- id: projects", "  assets: nested", "style:",
    "  page: {}", "fact_types:", "- id: identity", "assets:", "  logo: assets/logo.png", "provenance: {}", ""].join("\n");
  assert.deepEqual(technicalLines(text), [6, 8, 10, 12]);
});

test("a create or save reply is the new state, or on 422 the compile error", () => {
  const summary = { id: "custom-moy", name: "Мой", revision: "1.0.0", packageHash: "b".repeat(64) };
  const state = { schemaVersion: 1, package: summary, format: "yaml", text: "template: {}\n", bundled: false, edited: false };
  assert.deepEqual(parseSave(201, state), { saved: true, state: { package: summary, format: "yaml", text: "template: {}\n", bundled: false, edited: false } });
  assert.deepEqual(parseSave(422, { schemaVersion: 1, valid: false, package: null, error: { path: "/blocks/0", message: "bad" } }),
    { saved: false, error: { path: "/blocks/0", message: "bad" } });
  // A 422 that says valid, or a success without a state, is not trusted.
  assert.throws(() => parseSave(422, { schemaVersion: 1, valid: true, package: summary, error: null }), /INVALID_RESULT/);
  assert.throws(() => parseSave(201, { schemaVersion: 1, package: summary }), /INVALID_RESULT/);
});

test("a taken revision brings the free one Save offers; an empty or odd value offers none", () => {
  const refused = (nextRevision: unknown) => parseSave(422, { schemaVersion: 1, valid: false, package: null,
    error: { path: "/template/revision", message: "taken", nextRevision } });
  assert.deepEqual(refused("1.0.2"), { saved: false, error: { path: "/template/revision", message: "taken", nextRevision: "1.0.2" } });
  for (const value of ["", 3, null]) assert.deepEqual(refused(value), { saved: false, error: { path: "/template/revision", message: "taken" } });
});
