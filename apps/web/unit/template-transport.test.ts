import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import requestSchema from "../../../contracts/json-schema/background_writer_prepare_edit_v2.schema.json" with { type: "json" };
import type { WriterPrepareEditV2 } from "../src/contracts/generated/background_writer_prepare_edit_v2";
import type { PreparedSaveOpening } from "../src/contracts/template-save";
import { taggedSchema } from "../src/contracts/tagged-schema";
import { decodeJsonResponse } from "../src/contracts/json-response";
import { jsonWireAt, parseJsonWire } from "../src/contracts/lossless-json";
import { prepareTemplateTransport, saveTemplateTransport } from "../src/contracts/template-transport";
import { WriterApi } from "../src/background/api";
import { requestWire, RichApiFailure } from "../src/rich/api";

const fixture: unknown = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/preparation-transport.json", import.meta.url), "utf8"));
assert.ok(typeof fixture === "object" && fixture !== null && "cases" in fixture && Array.isArray(fixture.cases)
  && "opening" in fixture && typeof fixture.opening === "object" && fixture.opening !== null);
const evidence = fixture;
function wire(key: string): string {
  const value: unknown = Reflect.get(evidence, key); assert.equal(typeof value, "string");
  return String(value);
}
const base = parseJsonWire(wire("baseWire"));
const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const shape = ajv.compile<WriterPrepareEditV2>(taggedSchema(requestSchema));
function request(): WriterPrepareEditV2 {
  const root = parseJsonWire(wire("requestWire")); assert.ok(shape(root.value)); return root.value;
}
const rawOpening = fixture.opening;
function string(key: string): string { const value: unknown = Reflect.get(rawOpening, key); assert.equal(typeof value, "string"); return String(value); }
function number(key: string): number { const value: unknown = Reflect.get(rawOpening, key); assert.equal(typeof value, "number"); return Number(value); }
const opening: PreparedSaveOpening = { projectId: string("projectId"), lineage: string("lineage"), epoch: number("epoch"),
  sessionId: string("sessionId"), incarnation: string("incarnation"), actionCursor: number("actionCursor"),
  minimumTouchGeneration: number("minimumTouchGeneration") };
const replies = new Map(fixture.cases.map((row: unknown) => {
  assert.ok(typeof row === "object" && row !== null && "name" in row && typeof row.name === "string"
    && "replyWire" in row && typeof row.replyWire === "string");
  return [row.name, row.replyWire];
}));
function saved(name: string): unknown { const value = replies.get(name); assert.ok(value); return decodeJsonResponse(value); }
async function prepared() {
  return prepareTemplateTransport(opening.projectId, base, request(), async () => decodeJsonResponse(wire("replyWire")));
}

test("existing WriterApi prepares bound input and sends the exact registered compact mutation", async () => {
  const paths: string[] = [];
  const api = new WriterApi(opening.projectId, async (path, method, body) => {
    paths.push(path); assert.equal(method, "POST"); assert.ok(shape(body));
    assert.equal(body.preparationInputWire, request().preparationInputWire);
    return decodeJsonResponse(wire("replyWire"));
  }, async (path, body) => {
    paths.push(path);
    assert.equal(body.wire, parseJsonWire(wire("saveRequestWire")).wire);
    return saved("current");
  });
  const value = await api.templatePrepareDelta(base, request());
  const result = await api.templateSavePrepared(parseJsonWire(wire("advanceWire")), value, opening);
  assert.equal(result.kind, "committed");
  if (result.kind === "committed") assert.ok(result.acknowledgment.currentEqualsCommitted);
  assert.deepEqual(paths, [`/${opening.projectId}/writer/prepare-delta`, `/${opening.projectId}/writer/save`]);
});

test("preparation rejects an unbound input digest, canonical hash, request, capture or base", async () => {
  const source = wire("replyWire");
  const variants: (readonly [string, string])[] = [
    ["preparationInputSha256", "0".repeat(64)], ["requestHash", "0".repeat(64)],
  ];
  for (const [key, value] of variants) {
    const data: unknown = JSON.parse(source); assert.ok(typeof data === "object" && data !== null);
    Reflect.set(data, key, value);
    await assert.rejects(prepareTemplateTransport(opening.projectId, base, request(), async () => decodeJsonResponse(JSON.stringify(data))), /INVALID_RESULT/);
  }
  for (const key of ["request", "capture", "snapshot"] as const) {
    const changed = request();
    if (key === "request") changed.preparation.clientMutationId = "another-request";
    else if (key === "capture") changed.preparation.capture.actionToken++;
    else changed.preparation.snapshot.documentRevision++;
    await assert.rejects(prepareTemplateTransport(opening.projectId, base, changed, async () => decodeJsonResponse(source)), /INVALID_RESULT/);
  }
  await assert.rejects(prepareTemplateTransport("wrong-project", base, request(), async () => decodeJsonResponse(source)), /INVALID_RESULT/);
});

test("mutable input and decoded base cannot change a request frozen before awaiting", async () => {
  const input = request(), original = JSON.stringify(input), mutable = parseJsonWire(base.wire);
  const pending = prepareTemplateTransport(opening.projectId, mutable, input, async outbound => {
    assert.equal(outbound.preparation.clientMutationId, request().preparation.clientMutationId);
    input.preparation.capture.actionToken++;
    return decodeJsonResponse(wire("replyWire"));
  });
  input.preparation.clientMutationId = "changed-during-hash";
  assert.ok(typeof mutable.value === "object" && mutable.value !== null && "identity" in mutable.value);
  mutable.value.identity = { title: "unbacked", subtitle: "" };
  const result = await pending;
  assert.equal(result.requestWire, original);
  assert.equal(result.prepared.delta.clientMutationId, request().preparation.clientMutationId);
});

test("lost preparation responses retry one frozen identity rather than silently rebasing", async () => {
  const seen: string[] = [];
  const send = async (body: WriterPrepareEditV2) => {
    seen.push(JSON.stringify(body));
    if (seen.length === 1) throw new RichApiFailure("REQUEST_FAILED", 503);
    return decodeJsonResponse(wire("replyWire"));
  };
  const input = request();
  await assert.rejects(prepareTemplateTransport(opening.projectId, base, input, send), /REQUEST_FAILED/);
  await prepareTemplateTransport(opening.projectId, base, input, send);
  assert.equal(seen.length, 2); assert.equal(seen[0], seen[1]);
});

test("lost save replies retain original commit evidence across newer canonical state and recovery", async () => {
  const value = await prepared(), seen: string[] = [];
  const advance = parseJsonWire(wire("advanceWire"));
  await assert.rejects(saveTemplateTransport(opening.projectId, advance, value, opening, async body => {
    seen.push(body.wire); throw new RichApiFailure("REQUEST_FAILED", 503);
  }), /REQUEST_FAILED/);
  const result = await saveTemplateTransport(opening.projectId, advance, value, opening, async body => {
    seen.push(body.wire); return saved("historical");
  });
  assert.equal(result.kind, "committed");
  if (result.kind === "committed") {
    assert.equal(result.acknowledgment.currentEqualsCommitted, false);
    assert.ok(result.acknowledgment.currentCanonicalRevision > result.response.workspace.projectRevision);
    assert.equal(result.response.workspace.projectRevision, result.acknowledgment.replay.resultingRevision);
  }
  assert.equal(seen[0], seen[1]);
  const recovery = await saveTemplateTransport(opening.projectId, advance, value, opening, async () => saved("recovery"));
  assert.equal(recovery.kind, "committed_recovery_required");
  assert.equal("response" in recovery, false);
});

test("save freezes its opening and wire before awaiting and rejects a foreign opening before sending", async () => {
  const value = await prepared(), mutable = parseJsonWire(wire("advanceWire")), captured = { ...opening };
  const result = await saveTemplateTransport(opening.projectId, mutable, value, captured, async body => {
    assert.equal(body.wire, parseJsonWire(wire("saveRequestWire")).wire);
    captured.incarnation = "changed-opening";
    const proof = jsonWireAt(mutable, ["proof"]).value;
    assert.ok(typeof proof === "object" && proof !== null && "incarnation" in proof);
    proof.incarnation = "changed-decoded-input";
    return saved("current");
  });
  assert.equal(result.kind, "committed");
  await assert.rejects(saveTemplateTransport(opening.projectId, parseJsonWire(wire("advanceWire")), value,
    { ...opening, incarnation: "foreign-opening" }, async () => assert.fail("must not dispatch")), /INVALID_RESULT/);
});

test("raw HTTP writer transport preserves numeric lexemes and propagates uncertain errors", async () => {
  const previous = globalThis.fetch, body = parseJsonWire(wire("saveRequestWire"));
  globalThis.fetch = async (_url, init) => {
    assert.equal(init?.body, body.wire);
    return new Response('{"error":{"code":"OUTCOME_UNKNOWN"}}', { status: 409 });
  };
  try { await assert.rejects(requestWire(`/${opening.projectId}/writer/save`, body), error =>
    error instanceof RichApiFailure && error.code === "OUTCOME_UNKNOWN" && error.status === 409); }
  finally { globalThis.fetch = previous; }
});
