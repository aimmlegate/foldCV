import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { sha256 } from "../src/background/wire";
import { applyCanonicalPatch } from "../src/contracts/canonical-patch";
import { jsonObjectWire, jsonWireAt, parseJsonWire, type JsonWireNode } from "../src/contracts/lossless-json";
import { projectTemplateUi, templateBlockCell, templateBuiltinCell, templateUiChanges } from "../src/rich/template-ui";
import { SessionHistory } from "../src/rich/history";

function fixture(): JsonWireNode {
  const data: unknown = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/client-responses.json", import.meta.url), "utf8"));
  assert.ok(typeof data === "object" && data !== null && "authored" in data && typeof data.authored === "string"
    && "assets" in data && Array.isArray(data.assets));
  let wire = data.authored;
  for (const asset of data.assets as unknown[]) {
    assert.ok(typeof asset === "object" && asset !== null && "marker" in asset && typeof asset.marker === "string"
      && "path" in asset && typeof asset.path === "string");
    wire = wire.replaceAll(asset.marker, readFileSync(new URL(`../../../${asset.path}`, import.meta.url)).toString("base64"));
  }
  return parseJsonWire(wire);
}
const source = fixture();
const projectPath = "/workspace/project";
function locateField(node: JsonWireNode, path: readonly (string | number)[] = [], block: readonly (string | number)[] = []):
  { field: readonly (string | number)[]; block: readonly (string | number)[] } | null {
  if (node.children.has("provenance") && node.children.has("children")) block = path;
  if (node.children.get("type")?.value === "fact_field") return { field: path, block };
  for (const [key, child] of node.children) {
    const result = locateField(child, [...path, key], block);
    if (result) return result;
  }
  return null;
}
const location = locateField(jsonWireAt(source, ["workspace", "project", "document"]), ["workspace", "project", "document"]);
assert.ok(location);
const blockPath = `/${location.block.join("/")}`;
const fieldPath = `/${location.field.join("/")}`;
const recordPath = `${projectPath}/facts/records/0`;
const field = jsonWireAt(source, location.field);
assert.equal(jsonWireAt(field, ["type"]).value, "fact_field");
const blockId = jsonWireAt(source, [...location.block, "id"]).value;
const recordId = jsonWireAt(source, ["workspace", "project", "facts", "records", 0, "id"]).value;
assert.ok(typeof blockId === "string" && typeof recordId === "string");

type Edit = readonly [pointer: string, wire: string];
async function edit(input: JsonWireNode, edits: readonly Edit[]): Promise<JsonWireNode> {
  return applyCanonicalPatch(input, edits.map(([pointer, wire]) => ({ kind: "set", pointer, valueWire: parseJsonWire(wire).wire })));
}
async function sealed(edits: readonly Edit[], input = source): Promise<JsonWireNode> {
  let root = await edit(input, edits);
  const document = jsonWireAt(root, ["workspace", "project", "document"]), references: (readonly [string, string])[] = [];
  function visit(node: JsonWireNode): void {
    if (node.children.has("provenance") && node.children.has("children")) {
      const id = jsonWireAt(node, ["id"]).value; assert.equal(typeof id, "string");
      references.push([String(id), jsonWireAt(node, ["presentation"]).wire]);
    }
    node.children.forEach(visit);
  }
  visit(document);
  const blocks = jsonObjectWire(references), recipe = jsonWireAt(root, ["presentation", "recipe"]).wire;
  root = await edit(root, [["/presentation/blocks", blocks]]);
  for (const [key, hash] of [
    ["documentHash", await sha256(document.wire)],
    ["factsHash", await sha256(jsonWireAt(root, ["workspace", "project", "facts"]).wire)],
    ["presentationHash", await sha256(jsonObjectWire([["blocks", blocks], ["recipe", recipe]]))],
  ]) root = await edit(root, [[`/snapshot/${key}`, JSON.stringify(hash)], [`/presentation/snapshot/${key}`, JSON.stringify(hash)]]);
  return root;
}

test("UI projection owns verified wire and rejects corrupted or missing canonical evidence", async () => {
  const mutable = parseJsonWire(source.wire);
  const pending = projectTemplateUi(mutable);
  assert.ok(typeof mutable.value === "object" && mutable.value !== null && "identity" in mutable.value);
  mutable.value.identity = { title: "Unbacked title", subtitle: "" };
  const result = await pending;
  assert.equal(result.responseWire, source.wire);
  assert.equal(result.packageWire, jsonWireAt(source, ["workspace", "project", "templatePackage"]).wire);
  await assert.rejects(projectTemplateUi(await edit(source, [[`${fieldPath}/text`, '"unverified"']])), /INVALID_RESULT/);
});

test("monotonic named engine revisions do not make false UI history changes", async () => {
  const before = await projectTemplateUi(source);
  const after = await projectTemplateUi(await sealed([
    [`${blockPath}/revision`, "99"], [`${fieldPath}/syncedFactRevision`, "99"],
    [`${projectPath}/document/regions/2/revision`, "99"], [`${recordPath}/revision`, "99"],
    [`${recordPath}/employer/revision`, "99"], [`${recordPath}/periods/0/revision`, "99"],
    [`${recordPath}/periods/0/start/revision`, "99"],
  ]));
  assert.deepEqual(templateUiChanges(before, after), []);
  assert.notEqual(before.responseWire, after.responseWire);
  assert.equal(jsonWireAt(parseJsonWire(after.responseWire), ["workspace", "project", "facts", "records", 0, "employer", "revision"]).wire, "99");
});

test("source and citation revisions survive projection while text stays equal", async () => {
  const citation = jsonWireAt(source, ["workspace", "project", "facts", "records", 0, "evidence", 0]);
  for (const key of ["sourceRevision", "unitRevision"]) {
    const before = await projectTemplateUi(source);
    const after = await projectTemplateUi(await sealed([[`${recordPath}/evidence/0/${key}`, "99"]]));
    assert.deepEqual(templateUiChanges(before, after).map(change => change.key), [templateBuiltinCell(recordId)]);
  }
  assert.ok(citation.children.has("sourceRevision"));
});

test("equal wording cannot hide semantic identities, provenance or presentation", async () => {
  const before = await projectTemplateUi(source);
  const variants: Edit[] = [
    [`${fieldPath}/bindingRootId`, '"different-occurrence"'],
    [`${fieldPath}/cellId`, '"different-cell"'],
    [`${fieldPath}/complete`, "false"],
    [`${fieldPath}/presentation/overrides/size`, "10.5000000000000001"],
    [`${blockPath}/presentation/overrides/italic`, "true"],
    [`${blockPath}/provenance`, '[{"id":"citation-only","kind":"source","evidence":[{"sourceId":"source","sourceRevision":7,"unitId":"unit","unitRevision":9,"text":"same"}]}]'],
  ];
  for (const variant of variants) {
    const after = await projectTemplateUi(await sealed([variant]));
    const changes = templateUiChanges(before, after);
    assert.equal(changes.length, 1, variant[0]);
    assert.equal(changes[0]?.key, templateBlockCell(blockId));
    if (variant[0].endsWith("/size")) assert.ok(changes[0]?.after?.includes("10.5000000000000001"));
  }
});

test("raw period values retain pending text and stable period IDs in one builtin cell", async () => {
  const before = await projectTemplateUi(source);
  for (const variant of [
    [`${recordPath}/periods/0/start/rawText`, '"Spring, perhaps"'],
    [`${recordPath}/periods/0/start/pendingRawText`, '"later correction"'],
    [`${recordPath}/periods/0/id`, '"period:with:colons"'],
    [`${recordPath}/employer/rawText`, '"Human wording"'],
  ] as const) {
    const after = await projectTemplateUi(await sealed([variant]));
    assert.deepEqual(templateUiChanges(before, after).map(change => change.key), [templateBuiltinCell(recordId)]);
  }
});

test("issue-only canonical changes stay exact and can retain a zero-UI Undo action", async () => {
  const before = await projectTemplateUi(source);
  const after = await projectTemplateUi(await sealed([[`${projectPath}/importIssues/1/state`, '"retired"'],
    [`${projectPath}/importIssues/1/retiredByAction`, '"human-edit"'],
    [`${projectPath}/facts/builtinManualScopes`, '{"revision":"scope-revision"}']]));
  const changes = templateUiChanges(before, after);
  assert.deepEqual(changes, []);
  assert.equal(jsonWireAt(parseJsonWire(after.responseWire), ["workspace", "project", "facts", "builtinManualScopes", "revision"]).value, "scope-revision");
  assert.equal(jsonWireAt(parseJsonWire(after.responseWire), ["workspace", "project", "importIssues", 1, "state"]).value, "retired");
  const history = new SessionHistory("opening", before.cells, () => {}, () => true, "opening", "server");
  const action = history.commit("typing", changes);
  assert.ok(action);
  assert.equal(history.acknowledgeServerAction(action, 0, true), "retained");
  const reservation = history.reserveNavigation("undo", "undo");
  assert.ok(reservation && history.publishNavigation(reservation, "undo", []));
});

test("projection comparison cannot cross project or captured package ownership", async () => {
  const before = await projectTemplateUi(source);
  assert.throws(() => templateUiChanges(before, { ...before, projectId: "another-opening-project" }), /DEPENDENCY_CHANGED/);
  assert.throws(() => templateUiChanges(before, { ...before, packageWire: "another-package" }), /DEPENDENCY_CHANGED/);
});

test("table and nested link projections remove only their named engine counters", async () => {
  const link = jsonObjectWire([["type", '"bound_link"'], ["href", '"https://example.test"'],
    ["content", `[${field.wire}]`], ["labelBinding", "null"], ["urlBinding", "null"],
    ["presentation", jsonWireAt(field, ["presentation"]).wire]]);
  const content = `{"columnWidths":[100.0],"headerRows":0,"rows":[{"id":"row:1","cells":[{"id":"cell:1","revision":1,"content":[${link}]}]}]}`;
  const table = await sealed([[`${blockPath}/type`, '"table"'], [`${blockPath}/props`, "{}"], [`${blockPath}/content`, content]]);
  const before = await projectTemplateUi(table);
  const cell = `${blockPath}/content/rows/0/cells/0`;
  const after = await projectTemplateUi(await sealed([[`${cell}/revision`, "100"],
    [`${cell}/content/0/content/0/syncedFactRevision`, "100"]], table));
  assert.deepEqual(templateUiChanges(before, after), []);
  const bound = await projectTemplateUi(await sealed([[`${cell}/content/0/content/0/occurrenceId`, '"another-occurrence"']], table));
  assert.deepEqual(templateUiChanges(before, bound).map(change => change.key), [templateBlockCell(blockId)]);
});

test("manual scope identities and zero-length spans remain in authored UI cells", async () => {
  const scope = jsonObjectWire([["type", '"manual_scope"'], ["scopeId", '"scope:1"'], ["fragmentId", '"fragment:1"'],
    ["occurrenceId", '"occurrence:1"'], ["text", '""'], ["styles", "{}"],
    ["presentation", jsonWireAt(field, ["presentation"]).wire]]);
  const manual = await sealed([[fieldPath, scope]]);
  const before = await projectTemplateUi(manual);
  assert.ok(before.cells.get(templateBlockCell(blockId))?.includes('"scopeId":"scope:1"'));
  const after = await projectTemplateUi(await sealed([[`${fieldPath}/scopeId`, '"scope:2"']], manual));
  assert.deepEqual(templateUiChanges(before, after).map(change => change.key), [templateBlockCell(blockId)]);
});
