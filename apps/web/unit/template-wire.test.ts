import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { decodeJsonResponse } from "../src/contracts/json-response";
import { jsonObjectWire, jsonWireAt, parseJsonWire, type JsonWireNode } from "../src/contracts/lossless-json";
import { templateProjectReply, templateWriterReply } from "../src/contracts/template-validate";
import { templateProjectRequest } from "../src/rich/api";
import { WriterApi } from "../src/background/api";

function fixture(kind: "authored" | "writer" | "predraft" | "compiler1" | "compiler2" | "compiler3"): string {
  const filename = kind.startsWith("compiler") ? "client-compiler3.json" : "client-responses.json";
  const root: unknown = JSON.parse(readFileSync(new URL(`../../../tests/fixtures/synthetic/templates/${filename}`, import.meta.url), "utf8"));
  assert.ok(typeof root === "object" && root !== null && kind in root && "assets" in root && Array.isArray(root.assets));
  let source: unknown = Reflect.get(root, kind);
  assert.equal(typeof source, "string");
  for (const asset of root.assets as unknown[]) {
    assert.ok(typeof asset === "object" && asset !== null && "marker" in asset && typeof asset.marker === "string"
      && "path" in asset && typeof asset.path === "string");
    const base64 = readFileSync(new URL(`../../../${asset.path}`, import.meta.url)).toString("base64");
    if (typeof source === "string") source = source.replaceAll(asset.marker, base64);
  }
  assert.equal(typeof source, "string");
  return source as string;
}

function replace(source: string, path: readonly (string | number)[], wire: string): string {
  function visit(node: JsonWireNode, remaining: readonly (string | number)[]): string {
    const [key, ...rest] = remaining;
    if (key === undefined) return wire;
    const child = node.children.get(key);
    assert.ok(child);
    const changed = visit(child, rest);
    if (Array.isArray(node.value)) return `[${[...node.children].map(([id, value]) => id === key ? changed : value.wire).join(",")}]`;
    return jsonObjectWire([...node.children].map(([id, value]) => [String(id), id === key ? changed : value.wire]));
  }
  return visit(parseJsonWire(source), path);
}

test("Python authored/predraft and V2 writer replies retain exact snapshot and package evidence", async () => {
  for (const kind of ["authored", "predraft"] as const) {
    const value = await templateProjectReply(decodeJsonResponse(fixture(kind)));
    assert.ok(value, kind);
    assert.ok(await templateProjectReply(value), `${kind} retains evidence after validation`);
  }
  const writer = await templateWriterReply(decodeJsonResponse(fixture("writer")));
  assert.ok(writer?.canonicalReady && writer.localHistoryAck && writer.mutationWire);
  assert.equal(writer.response.snapshot?.documentHash, writer.response.presentation?.snapshot.documentHash);
});

test("retained compiler1/2 scientific meaning and compiler3 header packages pass integrity", async () => {
  for (const [kind, version] of [["compiler1", "template-compiler-1"], ["compiler2", "template-compiler-2"],
    ["compiler3", "template-compiler-3"]] as const) {
    const reply = await templateProjectReply(decodeJsonResponse(fixture(kind)));
    assert.ok(reply?.workspace.preDraft?.templatePackage, kind);
    const captured = reply.workspace.preDraft.templatePackage;
    assert.equal(captured.compilerVersion, version);
    if (kind === "compiler3") assert.ok(captured.recipe.capabilities.includes("header_slots"));
    else assert.equal(captured.definition.content_definitions["legacy-scientific"]?.["const"], "1e3");
  }
});

test("snapshot, presentation, asset and save-ack tampering cannot reuse a verified claimed package hash", async () => {
  const source = fixture("authored");
  assert.ok(await templateProjectReply(decodeJsonResponse(source)));
  const cases: (readonly [readonly (string | number)[], string])[] = [
    [["snapshot", "documentHash"], JSON.stringify("0".repeat(64))],
    [["snapshot", "factsHash"], JSON.stringify("0".repeat(64))],
    [["presentation", "recipe", "style", "page", "first_body_top"], "999.0"],
    [["workspace", "project", "templatePackage", "assets", 0, "bytesBase64"], '"Zm9yZ2Vk"'],
    [["workspace", "project", "templatePackage", "configHash"], JSON.stringify("0".repeat(64))],
    [["savedDocumentRevision"], "999"],
  ];
  for (const [path, wire] of cases) assert.equal(await templateProjectReply(decodeJsonResponse(replace(source, path, wire))), null, path.join("/"));
});

test("writer replay and local authority must match exact current workspace and action", async () => {
  const source = fixture("writer");
  for (const [path, wire] of [
    [["workspaceSha256"], JSON.stringify("0".repeat(64))],
    [["localHistoryAck", "actionId"], '"another-action"'],
    [["localHistoryAck", "generation"], "0"],
    [["mutationWire"], '"{}"'],
    [["response", "workspace", "title"], '"another-project-state"'],
  ] as const) assert.equal(await templateWriterReply(decodeJsonResponse(replace(source, path, wire))), null, path.join("/"));
});

test("plain parsed or changed response objects cannot supply retained numeric hash evidence", async () => {
  assert.equal(await templateProjectReply(JSON.parse(fixture("authored"))), null);
  const value = decodeJsonResponse(fixture("authored"));
  assert.ok(typeof value === "object" && value !== null && "savedDocumentRevision" in value);
  value.savedDocumentRevision = 999;
  assert.equal(await templateProjectReply(value), null);
});

test("mutable writer replies cannot alias negative zero or nonfinite numbers to retained JSON evidence", async () => {
  const first = await templateWriterReply(decodeJsonResponse(fixture("writer")));
  assert.ok(first?.response.workspace.project);
  const block = first.response.workspace.project.templatePackage.blocks[0];
  assert.ok(block);
  assert.equal(block.dependencyOrder, 0);
  block.dependencyOrder = -0;
  assert.equal(await templateWriterReply(first), null);
  const second = await templateWriterReply(decodeJsonResponse(fixture("writer")));
  assert.ok(second?.response.workspace.project);
  const observation = second.response.workspace.project.facts.observations.find(item => item.typedValue === null);
  assert.ok(observation);
  observation.typedValue = Number.NaN;
  assert.equal(await templateWriterReply(second), null);
});

test("existing HTTP transport and writer adapter validate canonical template replies", async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = async () => new Response(fixture("authored"), { headers: { "Content-Type": "application/json" } });
  try {
    const read = await templateProjectRequest("/pipeline-project");
    assert.equal(read.workspace.schemaVersion, 7);
  } finally { globalThis.fetch = previous; }
  const api = new WriterApi("pipeline-project", async () => decodeJsonResponse(fixture("writer")));
  assert.equal((await api.templateBootstrap()).schemaVersion, 2);
  const wrong = new WriterApi("other-project", async () => decodeJsonResponse(fixture("writer")));
  await assert.rejects(wrong.templateBootstrap(), /INVALID_RESULT/);
  const root = parseJsonWire(fixture("authored"));
  assert.equal(jsonWireAt(root, ["presentation", "recipe", "style", "page", "width"]).wire.includes("."), true);
});
