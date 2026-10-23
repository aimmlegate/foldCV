import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import mapSchema from "../../../contracts/json-schema/template_address_map_v1.schema.json" with { type: "json" };
import type { PreparedAddressMapV1 } from "../src/contracts/generated/template_address_map_v1";
import { parseJsonWire } from "../src/contracts/lossless-json";
import { contentText, responseBlocks, verifyAddressMap } from "../src/contracts/template-address";
import { sha256 } from "../src/background/wire";
import { taggedSchema } from "../src/contracts/tagged-schema";
import { containerKey, correctionRange, createdLocals, translateIntent, type LocalContainer, type Side, type V7Intent, type V7Operation } from "../src/rich/v7-translation";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const mapShape = ajv.compile<PreparedAddressMapV1>(taggedSchema(mapSchema));

function record(value: unknown): Record<string, unknown> {
  assert.ok(typeof value === "object" && value !== null && !Array.isArray(value));
  return Object.fromEntries(Object.entries(value));
}
function string(value: unknown): string { assert.equal(typeof value, "string"); return String(value); }
function number(value: unknown): number { assert.equal(typeof value, "number"); return Number(value); }
function container(value: unknown): LocalContainer {
  const raw = record(value), kind = raw["kind"], cell = raw["cellId"];
  assert.ok(kind === "content" || kind === "caption" || kind === "cell");
  assert.ok(cell === null || typeof cell === "string");
  return { blockId: string(raw["blockId"]), kind, cellId: cell };
}
function side(value: unknown): Side | null {
  assert.ok(value === null || value === "before" || value === "after" || value === "interior" || value === "anchor");
  return value;
}
function operation(value: unknown): V7Operation {
  const raw = record(value);
  if (raw["kind"] === "split_block") return { kind: "split_block", container: container(raw["container"]),
    offset: number(raw["offset"]), created: string(raw["created"]) };
  assert.equal(raw["kind"], "replace_text");
  const styles = record(raw["styles"]);
  return { kind: "replace_text", container: container(raw["container"]), start: number(raw["start"]), end: number(raw["end"]),
    text: string(raw["text"]), side: side(raw["side"]), styles: { bold: styles["bold"] === true, italic: styles["italic"] === true,
      underline: styles["underline"] === true, strike: styles["strike"] === true, code: styles["code"] === true,
      textColor: string(styles["textColor"]), backgroundColor: string(styles["backgroundColor"]) } };
}

type Chain = { name: string; result: string; map: PreparedAddressMapV1; locals: Map<string, string>; intent: V7Intent; expected: unknown };
const fixture = record(JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/address-chains.json", import.meta.url), "utf8")));
assert.ok(Array.isArray(fixture["cases"]));
const chains: Chain[] = fixture["cases"].map((row: unknown) => {
  const value = record(row), intent = record(value["intent"]), map: unknown = JSON.parse(string(value["mapWire"]));
  assert.ok(mapShape(map));
  return { name: string(value["name"]), result: string(value["resultWire"]), map,
    locals: new Map(Object.entries(record(value["locals"])).map(([key, item]) => [key, string(item)])),
    intent: { localId: string(intent["localId"]), operation: operation(intent["operation"]),
      prior: new Map(Object.entries(record(intent["prior"])).map(([key, item]) => [key, string(item)])) },
    expected: value["expected"] };
});
function chain(name: string): Chain { const value = chains.find(item => item.name === name); assert.ok(value); return value; }
function replacing(value: Chain, patch: { start?: number; end?: number; side?: Side | null }): Chain {
  const operation = value.intent.operation;
  assert.equal(operation.kind, "replace_text");
  if (operation.kind !== "replace_text") return value;
  return { ...value, intent: { ...value.intent, operation: { ...operation, ...patch } } };
}
function translate(value: Chain, map: PreparedAddressMapV1 | null = value.map) {
  return translateIntent(value.intent, { response: parseJsonWire(value.result), map, locals: value.locals });
}

test("buffered input reaches Python's named result piece from offset and side alone", () => {
  assert.ok(chains.length >= 18);
  for (const value of chains) {
    const result = translate(value), expected = record(value.expected);
    if (expected["kind"] === "conflict") assert.equal(result.kind, "conflict", value.name);
    else assert.deepEqual(result, value.expected, value.name);
  }
});

test("a server offer of no correspondence or a missing anchor keeps input as a conflict", () => {
  const value = chain("delayed-inserted-before"), map = structuredClone(value.map);
  for (const entry of map.containers) { entry.correspondence = "none"; entry.regions = []; entry.segments = []; entry.boundaries = []; }
  assert.equal(translate(value, map).kind, "conflict");
  assert.equal(translate(replacing(chain("empty-anchor"), { start: 5, end: 5 })).kind, "conflict");
});

test("unsupported targets and invalid ranges are conflicts, not nearby guesses", () => {
  const value = chain("delayed-inserted-before"), map = structuredClone(value.map);
  for (const boundary of map.containers[0]?.boundaries ?? []) if (boundary.offset === 9) boundary.before = null;
  assert.equal(translate(value, map).kind, "conflict");
  assert.equal(translate(replacing(value, { start: 100, end: 100 })).kind, "conflict");
  assert.equal(translate(replacing(value, { side: null })).kind, "conflict");
});

test("split results resolve the local created block only through the single created entry", () => {
  const value = chain("split-type-right"), split = chain("split-after-insert");
  const head: V7Intent = { localId: "op", prior: new Map(), operation: { kind: "split_block",
    container: { blockId: "block-paper-a", kind: "content", cellId: null }, offset: 8, created: "local-right" } };
  const resolved = createdLocals(head, { response: parseJsonWire(value.result), map: value.map, locals: new Map() });
  assert.deepEqual(resolved, value.locals);
  // Another operation's created slot cannot name this intent's local block.
  assert.equal(createdLocals({ ...head, localId: "another-op" }, { response: parseJsonWire(value.result), map: value.map, locals: new Map() }), null);
  assert.equal(createdLocals(head, { response: parseJsonWire(split.result), map: split.map, locals: new Map() }), null);
});

const maps = record(JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/address-maps.json", import.meta.url), "utf8")));
assert.ok(Array.isArray(maps["cases"]));
const typing = record(maps["cases"].find((row: unknown) => record(row)["name"] === "field-typing"));
async function verifiedBasis(change: (map: PreparedAddressMapV1) => void) {
  const map: unknown = JSON.parse(string(typing["mapWire"]));
  assert.ok(mapShape(map)); change(map);
  const wire = parseJsonWire(JSON.stringify(map)).wire, response = parseJsonWire(string(typing["resultWire"]));
  const created = record(typing["createdIds"]);
  const verified = await verifyAddressMap(parseJsonWire(wire), await sha256(wire), parseJsonWire(string(typing["baseWire"])), response, {
    clientMutationId: string(typing["clientMutationId"]), requestHash: string(typing["requestHash"]),
    createdIds: Object.fromEntries(Object.entries(created).map(([op, slots]) => [op, Object.fromEntries(
      Object.entries(record(slots)).map(([slot, identifier]) => [slot, string(identifier)]))])) });
  return { response, map: verified.map, locals: new Map<string, string>() };
}
const paper: LocalContainer = { blockId: "block-paper-a", kind: "content", cellId: null };
const styles = { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" };

test("review r2: every operation addressing a verified none output is a conflict", async () => {
  const basis = await verifiedBasis(map => {
    for (const entry of map.containers) { entry.correspondence = "none"; entry.regions = []; entry.segments = []; entry.boundaries = []; }
  });
  const text = (id: string) => contentText(responseBlocks(basis.response).get(id)?.groups[0]?.content ?? parseJsonWire("[]"));
  const trailing: LocalContainer = { blockId: "block-paper-b", kind: "content", cellId: null };
  const prior = new Map([[containerKey(paper), text("block-paper-a")], [containerKey(trailing), text("block-paper-b")]]);
  for (const operation of [
    { kind: "replace_text", container: paper, start: 5, end: 12, text: "Z", styles, side: null },
    { kind: "set_marks", container: paper, start: 5, end: 12, styles },
    { kind: "split_block", container: paper, offset: 9, created: "local-next" },
    { kind: "merge_blocks", leading: paper, trailing },
  ] satisfies V7Operation[]) assert.equal(translateIntent({ localId: "next", prior, operation }, basis).kind, "conflict", operation.kind);
});

test("review r2: a withheld address at a junction inside one leaf stays withheld on every side", async () => {
  const cut = 5;
  const basis = await verifiedBasis(map => {
    const entry = map.containers[0], first = entry?.segments[0];
    if (!entry || !first?.source) return;
    const second = structuredClone(first);
    first.result.end = cut; first.source.end = cut; second.result.start = cut;
    if (second.source) second.source.start = cut;
    first.target = null; second.target = null;
    entry.segments.splice(1, 0, second);
    entry.boundaries.push({ offset: cut, before: null, after: null });
    entry.boundaries.sort((a, b) => a.offset - b.offset);
  });
  const prior = new Map([[containerKey(paper), contentText(responseBlocks(basis.response).get("block-paper-a")?.groups[0]?.content ?? parseJsonWire("[]"))]]);
  for (const side of ["before", "after", "interior"] satisfies Side[]) {
    const result = translateIntent({ localId: "next", prior, operation: { kind: "replace_text", container: paper, start: cut, end: cut,
      text: "Z", styles, side } }, basis);
    assert.equal(result.kind, "conflict", side);
  }
});

test("correction ranges only bound the change and never split a surrogate pair", () => {
  assert.equal(correctionRange("same", "same"), null);
  assert.deepEqual(correctionRange("abc", "abXc"), { start: 2, end: 2, text: "X" });
  assert.deepEqual(correctionRange("aa", "aaa"), { start: 2, end: 2, text: "a" });
  assert.deepEqual(correctionRange("abc", ""), { start: 0, end: 3, text: "" });
  assert.deepEqual(correctionRange("a😀b", "a😃b"), { start: 1, end: 3, text: "😃" });
  assert.deepEqual(correctionRange("x😀", "x😀😀"), { start: 3, end: 3, text: "😀" });
  for (const [canonical, editor] of [["😀a", "😃a"], ["a😀", "a😃"], ["ab", "a😀b"], ["😀😀", "😀"]] as const) {
    const range = correctionRange(canonical, editor);
    assert.ok(range);
    const rebuilt = canonical.slice(0, range.start) + range.text + canonical.slice(range.end);
    assert.equal(rebuilt, editor);
    for (const point of [range.start, range.end]) {
      const left = canonical.charCodeAt(point - 1), right = canonical.charCodeAt(point);
      assert.ok(!(left >= 0xd800 && left <= 0xdbff && right >= 0xdc00 && right <= 0xdfff), `${canonical}->${editor}`);
    }
  }
});
