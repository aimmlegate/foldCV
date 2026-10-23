import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import mapSchema from "../../../contracts/json-schema/template_address_map_v1.schema.json" with { type: "json" };
import requestSchema from "../../../contracts/json-schema/background_writer_prepare_edit_v2.schema.json" with { type: "json" };
import { sha256 } from "../src/background/wire";
import { decodeJsonResponse } from "../src/contracts/json-response";
import { parseJsonWire } from "../src/contracts/lossless-json";
import { verifyAddressMap, type AddressExpectation } from "../src/contracts/template-address";
import { taggedSchema } from "../src/contracts/tagged-schema";
import { prepareTemplateTransport } from "../src/contracts/template-transport";
import type { WriterPrepareEditV2 } from "../src/contracts/generated/background_writer_prepare_edit_v2";
import type { PreparedAddressMapV1 } from "../src/contracts/generated/template_address_map_v1";

type Case = { name: string; clientMutationId: string; requestHash: string; createdIds: Record<string, Record<string, string>>;
  mapSha256: string; mapWire: string; baseWire: string; resultWire: string };

function record(value: unknown): Record<string, unknown> {
  assert.ok(typeof value === "object" && value !== null && !Array.isArray(value));
  return Object.fromEntries(Object.entries(value));
}
function string(value: unknown): string { assert.equal(typeof value, "string"); return String(value); }
const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const mapShape = ajv.compile<PreparedAddressMapV1>(taggedSchema(mapSchema));
const requestShape = ajv.compile<WriterPrepareEditV2>(taggedSchema(requestSchema));

const fixture = record(JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/address-maps.json", import.meta.url), "utf8")));
assert.ok(Array.isArray(fixture["cases"]));
const cases: Case[] = fixture["cases"].map((row: unknown) => {
  const value = record(row), created = record(value["createdIds"]);
  return { name: string(value["name"]), clientMutationId: string(value["clientMutationId"]), requestHash: string(value["requestHash"]),
    createdIds: Object.fromEntries(Object.entries(created).map(([key, slots]) => [key, Object.fromEntries(
      Object.entries(record(slots)).map(([slot, identifier]) => [slot, string(identifier)]))])),
    mapSha256: string(value["mapSha256"]), mapWire: string(value["mapWire"]), baseWire: string(value["baseWire"]),
    resultWire: string(value["resultWire"]) };
});
function named(name: string): Case {
  const value = cases.find(item => item.name === name); assert.ok(value); return value;
}
function expectation(value: Case): AddressExpectation {
  return { clientMutationId: value.clientMutationId, requestHash: value.requestHash, createdIds: value.createdIds };
}
function verify(value: Case, map = value.mapWire, hash = value.mapSha256, base = value.baseWire, result = value.resultWire,
  expected = expectation(value)) {
  return verifyAddressMap(parseJsonWire(map), hash, parseJsonWire(base), parseJsonWire(result), expected);
}
function mapOf(value: Case): PreparedAddressMapV1 {
  const parsed: unknown = JSON.parse(value.mapWire);
  assert.ok(mapShape(parsed));
  return parsed;
}
async function tampered(value: Case, change: (map: PreparedAddressMapV1) => void): Promise<void> {
  const map = mapOf(value); change(map);
  const wire = parseJsonWire(JSON.stringify(map)).wire;
  await assert.rejects(verify(value, wire, await sha256(wire)), /INVALID_RESULT/);
}

test("every Python fixture map verifies against its exact base and result", async () => {
  assert.ok(cases.length >= 12);
  for (const value of cases) {
    const verified = await verify(value);
    assert.equal(verified.sha256, value.mapSha256, value.name);
    assert.equal(verified.wire, parseJsonWire(value.mapWire).wire, value.name);
  }
  const typed = (await verify(named("field-typing"))).map.containers[0];
  assert.ok(typed);
  assert.deepEqual(typed.segments.map(segment => segment.role), ["retained_prefix", "inserted", "retained_suffix"]);
  assert.equal((await verify(named("no-op"))).map.containers.length, 0);
  const split = (await verify(named("split"))).map.containers;
  assert.equal(split.length, 2); assert.ok(split[1]?.created);
  assert.equal((await verify(named("copy-none"))).map.containers[0]?.correspondence, "none");
});

test("hash, request, snapshot and created identities bind the map to its preparation", async () => {
  const value = named("split");
  await assert.rejects(verify(value, value.mapWire, "0".repeat(64)), /INVALID_RESULT/);
  await assert.rejects(verify(value, value.mapWire, value.mapSha256, value.baseWire, value.resultWire,
    { ...expectation(value), clientMutationId: "another" }), /INVALID_RESULT/);
  await assert.rejects(verify(value, value.mapWire, value.mapSha256, value.baseWire, value.resultWire,
    { ...expectation(value), requestHash: "1".repeat(64) }), /INVALID_RESULT/);
  await assert.rejects(verify(value, value.mapWire, value.mapSha256, value.resultWire, value.resultWire), /INVALID_RESULT/);
  const slots = Object.fromEntries(Object.entries(value.createdIds).map(([op, values]) => [op,
    Object.fromEntries(Object.entries(values).map(([slot, identifier]) => [slot, identifier + "-other"]))]));
  await assert.rejects(verify(value, value.mapWire, value.mapSha256, value.baseWire, value.resultWire,
    { ...expectation(value), createdIds: slots }), /INVALID_RESULT/);
});

test("rehashed structural lies are still rejected against the workspaces", async () => {
  const typing = named("field-typing");
  await tampered(typing, map => { map.containers.pop(); });
  await tampered(typing, map => {
    const segment = map.containers[0]?.segments[0];
    if (segment?.source?.span.kind === "field") segment.source.span.bindingId = "binding-journal";
  });
  await tampered(typing, map => {
    const segment = map.containers[0]?.segments[1];
    if (segment?.result.span.kind === "field") segment.result.span.occurrenceId = "occurrence-journal";
  });
  await tampered(typing, map => { const entry = map.containers[0]; if (entry) entry.afterContentHash = "2".repeat(64); });
  await tampered(typing, map => { const entry = map.containers[0]; if (entry) entry.segments[1]!.slot = null; });
  // Omitting a changed leaf, even with matching boundaries, must not pass as unchanged.
  await tampered(typing, map => {
    const entry = map.containers[0]; if (!entry) return;
    entry.segments.splice(2, 1);
    const edges = new Set(entry.segments.flatMap(segment => [segment.result.start, segment.result.end]));
    entry.boundaries = entry.boundaries.filter(boundary => edges.has(boundary.offset));
  });
  await tampered(named("split"), map => { const entry = map.containers[1]; if (entry) entry.created = null; });
  await tampered(named("scope-repeat-detach"), map => {
    const entry = map.containers.find(value => value.regions[0]?.role === "retained");
    const segment = entry?.segments[0];
    if (segment?.result.span.kind === "literal" && segment.source) segment.result.span = segment.source.span;
  });
  await tampered(named("merge"), map => { const entry = map.containers[1]; if (entry) entry.regions = []; });
});

test("incoherent maps fail before any workspace lookup", async () => {
  const typing = named("field-typing");
  await tampered(typing, map => { map.containers[0]?.segments.reverse(); });
  await tampered(typing, map => { map.containers[0]?.boundaries.pop(); });
  await tampered(typing, map => { const region = map.containers[0]?.regions[1]; if (region) region.result.start += 1; });
  await tampered(typing, map => { const entry = map.containers[0]; if (entry) entry.correspondence = "none"; });
  await tampered(typing, map => { map.resultSnapshot = map.baseSnapshot; });
});

test("bound transport verifies the reply map before returning a preparation", async () => {
  const transport = record(JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/preparation-transport.json", import.meta.url), "utf8")));
  const base = parseJsonWire(string(transport["baseWire"])), reply = string(transport["replyWire"]);
  const request = (): WriterPrepareEditV2 => {
    const value: unknown = JSON.parse(string(transport["requestWire"]));
    assert.ok(requestShape(value));
    return value;
  };
  const project = string(record(transport["opening"])["projectId"]);
  const accepted = await prepareTemplateTransport(project, base, request(), async () => decodeJsonResponse(reply));
  assert.equal(accepted.address.sha256, record(JSON.parse(reply))["addressMapSha256"]);
  assert.ok(accepted.address.map.containers.length);
  const changed = record(JSON.parse(reply)); changed["addressMapSha256"] = "0".repeat(64);
  await assert.rejects(prepareTemplateTransport(project, base, request(), async () => decodeJsonResponse(JSON.stringify(changed))), /INVALID_RESULT/);
});

test("review r1: partial leaf coverage and foreign targets are rejected after rehashing", async () => {
  const typing = named("field-typing");
  await tampered(typing, map => {
    const entry = map.containers[0], first = entry?.segments[0];
    if (!entry || !first?.source) return;
    first.result.end--; first.source.end--;
    const edges = new Set(entry.segments.flatMap(segment => [segment.result.start, segment.result.end]));
    entry.boundaries = entry.boundaries.filter(boundary => edges.has(boundary.offset));
    entry.boundaries.push({ offset: first.result.end, before: null, after: null });
    entry.boundaries.sort((a, b) => a.offset - b.offset);
  });
  await tampered(typing, map => { const segment = map.containers[0]?.segments[1]; if (segment) segment.target = { kind: "field", bindingId: "binding-journal" }; });
  await tampered(typing, map => { const boundary = map.containers[0]?.boundaries[0]; if (boundary) boundary.after = { kind: "manual_scope", fragmentId: "does-not-exist" }; });
  await tampered(typing, map => { const boundary = map.containers[0]?.boundaries[0]; if (boundary) boundary.before = { kind: "field", bindingId: "fragment-paper-a" }; });
  // Null stays acceptable: it only withholds an address and keeps later input as a conflict.
  const map = mapOf(typing), segment = map.containers[0]?.segments[1];
  assert.ok(segment); segment.target = null;
  const wire = parseJsonWire(JSON.stringify(map)).wire;
  await verify(typing, wire, await sha256(wire));
});
