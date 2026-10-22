import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import schema from "../../../contracts/json-schema/template_prepared_edit_delta_v1.schema.json" with { type: "json" };
import type { TemplatePreparedEditDeltaV1 } from "../src/contracts/generated/template_prepared_edit_delta_v1";
import { sha256 } from "../src/background/wire";
import { applyCanonicalPatch } from "../src/contracts/canonical-patch";
import { jsonWireAt, parseJsonWire } from "../src/contracts/lossless-json";
import { taggedSchema } from "../src/contracts/tagged-schema";
import { applyPreparedTemplateDelta } from "../src/contracts/template-delta";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const validDelta = ajv.compile<TemplatePreparedEditDeltaV1>(taggedSchema(schema));
const fixture: unknown = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/prepared-delta.json", import.meta.url), "utf8"));
assert.ok(typeof fixture === "object" && fixture !== null && "baseWire" in fixture && typeof fixture.baseWire === "string"
  && "cases" in fixture && Array.isArray(fixture.cases));
const base = parseJsonWire(fixture.baseWire);
const cases = fixture.cases.map((row: unknown) => {
  assert.ok(typeof row === "object" && row !== null && "name" in row && typeof row.name === "string"
    && "deltaWire" in row && typeof row.deltaWire === "string" && "responseSha256" in row && typeof row.responseSha256 === "string"
    && "workspaceSha256" in row && typeof row.workspaceSha256 === "string");
  const root = parseJsonWire(row.deltaWire), delta = root.value;
  assert.ok(validDelta(delta));
  return { name: row.name, root, delta, responseHash: row.responseSha256, workspaceHash: row.workspaceSha256 };
});

test("Python typing, issue, marks and no-op deltas reproduce exact server response bytes", async () => {
  for (const row of cases) {
    const result = await applyPreparedTemplateDelta(base, row.root, row.delta);
    assert.equal(await sha256(result.responseWire.wire), row.responseHash, row.name);
    assert.equal(await sha256(result.workspaceWire.wire), row.workspaceHash, row.name);
    assert.equal(result.response.identity?.title ?? null, row.delta.resultIdentity?.title ?? null);
    if (row.name === "typing") assert.equal(result.response.workspace.project?.importIssues[0]?.state, "retired");
    if (row.name === "marks") assert.equal(result.response.workspace.project?.importIssues[0]?.state, "active");
    if (row.name === "noop") assert.equal(result.responseWire.wire, base.wire);
  }
});

test("adoption binds returned values to authoritative bytes despite caller mutations", async () => {
  const row = cases.find(value => value.name === "noop");
  assert.ok(row);
  const mutableBase = parseJsonWire(base.wire), mutableRoot = parseJsonWire(row.root.wire);
  assert.ok(typeof mutableBase.value === "object" && mutableBase.value !== null && "identity" in mutableBase.value);
  assert.ok(validDelta(mutableRoot.value));
  const expected = structuredClone(mutableRoot.value);
  mutableBase.value.identity = { title: "Unbacked title", subtitle: "" };
  mutableRoot.value.capture.actionToken++;
  const result = await applyPreparedTemplateDelta(mutableBase, mutableRoot, expected);
  assert.deepEqual(result.delta, JSON.parse(row.root.wire));
  assert.deepEqual(result.response, JSON.parse(result.responseWire.wire));
  assert.equal(await sha256(result.responseWire.wire), row.responseHash);
});

test("caller mutations during asynchronous verification cannot change adopted or expected values", async () => {
  const row = cases.find(value => value.name === "typing");
  assert.ok(row);
  const mutableBase = parseJsonWire(base.wire), mutableRoot = parseJsonWire(row.root.wire);
  assert.ok(typeof mutableBase.value === "object" && mutableBase.value !== null && "identity" in mutableBase.value);
  assert.ok(validDelta(mutableRoot.value));
  const expected = structuredClone(mutableRoot.value);
  const pending = applyPreparedTemplateDelta(mutableBase, mutableRoot, expected);
  mutableBase.value.identity = { title: "Unbacked title", subtitle: "" };
  mutableRoot.value.capture.actionToken++;
  mutableRoot.value.resultIdentity = { title: "Unbacked result", subtitle: "" };
  expected.capture.actionToken++;
  const result = await pending;
  assert.deepEqual(result.delta, JSON.parse(row.root.wire));
  assert.deepEqual(result.response, JSON.parse(result.responseWire.wire));
  assert.equal(await sha256(result.responseWire.wire), row.responseHash);
});

test("stale capture, corrupt hashes, duplicate IDs, patch overlap and presentation loss reject", async () => {
  const row = cases.find(value => value.name === "typing");
  assert.ok(row);
  const variants: ((delta: TemplatePreparedEditDeltaV1) => void)[] = [
    delta => { delta.capture.actionToken++; },
    delta => { delta.requestHash = "0".repeat(64); },
    delta => { delta.baseWorkspaceSha256 = "0".repeat(64); },
    delta => { delta.resultWorkspaceSha256 = "0".repeat(64); },
    delta => { delta.createdIds = { text: { a: "same", b: "same" } }; },
    delta => { delta.workspacePatch.push(...delta.workspacePatch); },
    delta => { delta.presentationPatch.remove.push("missing-block"); },
    delta => { delta.presentationPatch.afterHash = "0".repeat(64); },
    delta => { delta.resultSnapshot.documentHash = "0".repeat(64); },
    delta => { delta.clientMutationId = "another-mutation"; },
  ];
  for (const change of variants) {
    const delta = structuredClone(row.delta); change(delta);
    await assert.rejects(applyPreparedTemplateDelta(base, parseJsonWire(JSON.stringify(delta)), row.delta), /INVALID_RESULT/);
  }
  const damagedBase = parseJsonWire(base.wire.replace('"projectRevision":1', '"projectRevision":999'));
  await assert.rejects(applyPreparedTemplateDelta(damagedBase, row.root, row.delta), /INVALID_RESULT/);
});

test("a matching result hash cannot authorize changing the captured package", async () => {
  const row = cases.find(value => value.name === "typing");
  assert.ok(row);
  const delta = structuredClone(row.delta);
  delta.workspacePatch.push({ kind: "set", pointer: "/project/templatePackage/id", valueWire: '"replacement"' });
  const altered = await applyCanonicalPatch(jsonWireAt(base, ["workspace"]), delta.workspacePatch);
  delta.resultWorkspaceSha256 = await sha256(altered.wire);
  await assert.rejects(applyPreparedTemplateDelta(base, parseJsonWire(JSON.stringify(delta)), row.delta), /INVALID_RESULT/);
});

test("no-op cannot change server metadata or allocate new identities", async () => {
  const row = cases.find(value => value.name === "noop");
  assert.ok(row);
  const metadata = structuredClone(row.delta);
  metadata.resultIdentity = { title: "Another identity", subtitle: "" };
  await assert.rejects(applyPreparedTemplateDelta(base, parseJsonWire(JSON.stringify(metadata)), row.delta), /INVALID_RESULT/);
  const allocation = structuredClone(row.delta); allocation.createdIds = { text: { unused: "new-id" } };
  await assert.rejects(applyPreparedTemplateDelta(base, parseJsonWire(JSON.stringify(allocation)), row.delta), /INVALID_RESULT/);
});
