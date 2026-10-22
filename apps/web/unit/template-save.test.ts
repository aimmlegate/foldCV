import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import schema from "../../../contracts/json-schema/background_writer_prepared_save_result_v2.schema.json" with { type: "json" };
import type { WriterPreparedSaveResultV2 } from "../src/contracts/generated/background_writer_prepared_save_result_v2";
import { sha256 } from "../src/background/wire";
import { applyCanonicalPatch } from "../src/contracts/canonical-patch";
import { jsonWireAt, parseJsonWire } from "../src/contracts/lossless-json";
import { taggedSchema } from "../src/contracts/tagged-schema";
import { applyPreparedTemplateDelta } from "../src/contracts/template-delta";
import { verifyPreparedTemplateSave, type PreparedSaveOpening } from "../src/contracts/template-save";
import deltaSchema from "../../../contracts/json-schema/template_prepared_edit_delta_v1.schema.json" with { type: "json" };
import type { TemplatePreparedEditDeltaV1 } from "../src/contracts/generated/template_prepared_edit_delta_v1";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const resultShape = ajv.compile<WriterPreparedSaveResultV2>(taggedSchema(schema));
const deltaShape = ajv.compile<TemplatePreparedEditDeltaV1>(taggedSchema(deltaSchema));
const fixture: unknown = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/committed-delta.json", import.meta.url), "utf8"));
assert.ok(typeof fixture === "object" && fixture !== null && "baseWire" in fixture && typeof fixture.baseWire === "string"
  && "deltaWire" in fixture && typeof fixture.deltaWire === "string" && "opening" in fixture
  && typeof fixture.opening === "object" && fixture.opening !== null && "cases" in fixture && Array.isArray(fixture.cases));
const rawOpening = fixture.opening;
assert.ok("projectId" in rawOpening && typeof rawOpening.projectId === "string"
  && "lineage" in rawOpening && typeof rawOpening.lineage === "string"
  && "epoch" in rawOpening && typeof rawOpening.epoch === "number"
  && "sessionId" in rawOpening && typeof rawOpening.sessionId === "string"
  && "incarnation" in rawOpening && typeof rawOpening.incarnation === "string"
  && "actionCursor" in rawOpening && typeof rawOpening.actionCursor === "number"
  && "minimumTouchGeneration" in rawOpening && typeof rawOpening.minimumTouchGeneration === "number");
const opening: PreparedSaveOpening = { projectId: rawOpening.projectId, lineage: rawOpening.lineage, epoch: rawOpening.epoch,
  sessionId: rawOpening.sessionId, incarnation: rawOpening.incarnation, actionCursor: rawOpening.actionCursor,
  minimumTouchGeneration: rawOpening.minimumTouchGeneration };
const base = parseJsonWire(fixture.baseWire), deltaRoot = parseJsonWire(fixture.deltaWire);
assert.ok(deltaShape(deltaRoot.value));
const expectedDelta = deltaRoot.value;
const cases = fixture.cases.map((row: unknown) => {
  assert.ok(typeof row === "object" && row !== null && "name" in row && typeof row.name === "string"
    && "ackWire" in row && typeof row.ackWire === "string" && "responseSha256" in row
    && (row.responseSha256 === null || typeof row.responseSha256 === "string"));
  const root = parseJsonWire(row.ackWire);
  assert.ok(resultShape(root.value));
  return { name: row.name, root, acknowledgment: root.value, responseHash: row.responseSha256 };
});
async function preview() { return (await applyPreparedTemplateDelta(base, deltaRoot, expectedDelta)).responseWire; }

test("compact current, historical and expired-proof replies preserve exact server commit identity", async () => {
  const prepared = await preview();
  for (const row of cases) {
    const result = await verifyPreparedTemplateSave(prepared, deltaRoot, row.root, opening);
    if (result.kind === "committed") {
      assert.equal(await sha256(result.responseWire.wire), row.responseHash);
      assert.equal(result.response.workspace.projectRevision, result.acknowledgment.replay.resultingRevision);
      assert.equal(result.response.generation?.id, result.acknowledgment.committedGeneration?.id);
      assert.equal(result.acknowledgment.currentEqualsCommitted, row.name === "current");
      if (row.name === "historical") assert.ok(result.acknowledgment.currentCanonicalRevision > result.response.workspace.projectRevision);
    } else {
      assert.equal(row.name, "recovery");
      assert.ok(!("response" in result) && !("localHistoryAck" in result.acknowledgment));
    }
  }
});

test("compact save rejects stale opening, unbound preparation, replay, cursor and commit evidence", async () => {
  const prepared = await preview(), row = cases.find(value => value.name === "current");
  assert.ok(row && row.acknowledgment.kind === "committed");
  type Commit = Extract<WriterPreparedSaveResultV2, { kind: "committed" }>;
  const variants: ((value: Commit) => void)[] = [
    value => { value.preparationRequestHash = "0".repeat(64); },
    value => { value.mutationSha256 = "0".repeat(64); },
    value => { value.replay.requestSha256 = "0".repeat(64); },
    value => { value.replay.resultingRevision++; },
    value => { value.writer.incarnation = "another-opening"; },
    value => { value.commitBinding.actionCursor++; },
    value => { value.commitBinding.touchGeneration = value.writer.touchGeneration + 1; },
    value => { value.preparedWorkspaceSha256 = "0".repeat(64); },
    value => { value.committedWorkspaceSha256 = "0".repeat(64); },
    value => { value.committedSnapshot.packageHash = "0".repeat(64); },
    value => { value.currentEqualsCommitted = false; },
    value => { value.commitPatch.push(...value.commitPatch); },
    value => { value.localHistoryAck = { actionId: "another-action", generation: 1 }; },
  ];
  for (const change of variants) {
    const damaged = structuredClone(row.acknowledgment); change(damaged);
    await assert.rejects(verifyPreparedTemplateSave(prepared, deltaRoot, parseJsonWire(JSON.stringify(damaged)), opening), /INVALID_RESULT/);
  }
  await assert.rejects(verifyPreparedTemplateSave(prepared, deltaRoot, row.root, { ...opening, lineage: "another-lineage" }), /INVALID_RESULT/);
  await assert.rejects(verifyPreparedTemplateSave(base, deltaRoot, row.root, opening), /INVALID_RESULT/);
});

test("a matching forged commit hash cannot authorize changing metadata other than the commit clock", async () => {
  const prepared = await preview(), row = cases.find(value => value.name === "current");
  assert.ok(row && row.acknowledgment.kind === "committed");
  const damaged = structuredClone(row.acknowledgment);
  damaged.commitPatch.push({ kind: "set", pointer: "/mutationReplay/0/resultingRevision", valueWire: "999" });
  const workspace = await applyCanonicalPatch(jsonWireAt(prepared, ["workspace"]), damaged.commitPatch);
  damaged.committedWorkspaceSha256 = await sha256(workspace.wire);
  damaged.currentCanonicalSha256 = damaged.committedWorkspaceSha256;
  await assert.rejects(verifyPreparedTemplateSave(prepared, deltaRoot, parseJsonWire(JSON.stringify(damaged)), opening), /INVALID_RESULT/);
});

test("recovery replies still require exact prepared request and durable mutation identity", async () => {
  const prepared = await preview(), row = cases.find(value => value.name === "recovery");
  assert.ok(row);
  const damaged = structuredClone(row.acknowledgment); damaged.preparationRequestHash = "0".repeat(64);
  await assert.rejects(verifyPreparedTemplateSave(prepared, deltaRoot, parseJsonWire(JSON.stringify(damaged)), opening), /INVALID_RESULT/);
});

test("mutable caller trees and opening objects cannot change verified save values during awaits", async () => {
  const row = cases.find(value => value.name === "current");
  assert.ok(row);
  const prepared = await preview(), root = parseJsonWire(row.root.wire), ownOpening = { ...opening };
  assert.ok(resultShape(root.value) && root.value.kind === "committed");
  root.value.committedIdentity = { title: "Unbacked metadata", subtitle: "" };
  const pending = verifyPreparedTemplateSave(prepared, deltaRoot, root, ownOpening);
  root.value.replay.resultingRevision++;
  ownOpening.incarnation = "another-opening";
  const result = await pending;
  assert.equal(result.kind, "committed");
  assert.deepEqual(result.acknowledgment, JSON.parse(row.root.wire));
  if (result.kind === "committed") assert.equal(await sha256(result.responseWire.wire), row.responseHash);
});
