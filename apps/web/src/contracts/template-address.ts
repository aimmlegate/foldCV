import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import mapSchema from "../../../../contracts/json-schema/template_address_map_v1.schema.json" with { type: "json" };
import type { PreparedAddressMapV1 } from "./generated/template_address_map_v1";
import { sha256 } from "../background/wire";
import { jsonObjectWire, jsonWireAt, parseJsonWire, type JsonWireNode } from "./lossless-json";
import { taggedSchema } from "./tagged-schema";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const mapShape = ajv.compile<PreparedAddressMapV1>(taggedSchema(mapSchema));

export type AddressContainer = PreparedAddressMapV1["containers"][number];
export type ContainerRef = AddressContainer["output"];
export type SpanRef = AddressContainer["segments"][number]["result"]["span"];
export type AddressExpectation = {
  clientMutationId: string;
  requestHash: string;
  createdIds: Readonly<Record<string, Readonly<Record<string, string>>>>;
};
export type VerifiedAddressMap = { map: PreparedAddressMapV1; wire: string; sha256: string };

export type AddressLeaf = { path: [number] | [number, number]; span: JsonWireNode; owner: JsonWireNode | null; start: number; end: number };
export type AddressTarget = NonNullable<AddressContainer["segments"][number]["target"]>;
export type AddressGroup = { kind: ContainerRef["kind"]; key: string; content: JsonWireNode; cellRevision: number | null };
export type AddressBlock = { node: JsonWireNode; revision: number; groups: AddressGroup[] };

function invalid(): never { throw new Error("INVALID_RESULT"); }
function at(node: JsonWireNode, key: string | number): JsonWireNode { return jsonWireAt(node, [key]); }
function text(node: JsonWireNode, key: string): string {
  const value = at(node, key).value;
  return typeof value === "string" ? value : invalid();
}
function optionalText(node: JsonWireNode, key: string): string | null {
  const value = at(node, key).value;
  return value === null ? null : typeof value === "string" ? value : invalid();
}
function integer(node: JsonWireNode, key: string): number {
  const value = at(node, key).value;
  return typeof value === "number" && Number.isSafeInteger(value) ? value : invalid();
}
function items(node: JsonWireNode): JsonWireNode[] { return Array.isArray(node.value) ? [...node.children.values()] : invalid(); }
function canonicalValue(value: unknown): string { return parseJsonWire(JSON.stringify(value)).wire; }

function groups(block: JsonWireNode): AddressGroup[] {
  const type = text(block, "type");
  if (type === "table") return items(at(at(block, "content"), "rows")).flatMap(row => items(at(row, "cells")).map(cell => ({
    kind: "cell" as const, key: text(cell, "id"), content: at(cell, "content"), cellRevision: integer(cell, "revision") })));
  if (type === "image") return [{ kind: "caption", key: "caption", content: at(at(block, "props"), "caption"), cellRevision: null }];
  const content = block.children.get("content");
  return content && Array.isArray(content.value) ? [{ kind: "content", key: "content", content, cellRevision: null }] : [];
}

export function responseBlocks(response: JsonWireNode): Map<string, AddressBlock> {
  const result = new Map<string, AddressBlock>();
  const visit = (node: JsonWireNode): void => {
    const id = text(node, "id");
    if (result.has(id)) invalid();
    result.set(id, { node, revision: integer(node, "revision"), groups: groups(node) });
    items(at(node, "children")).forEach(visit);
  };
  items(jsonWireAt(response, ["workspace", "project", "document", "regions"])).forEach(region => items(at(region, "blocks")).forEach(visit));
  return result;
}

export function addressLeaves(content: JsonWireNode): AddressLeaf[] {
  const result: AddressLeaf[] = [];
  let cursor = 0;
  items(content).forEach((span, index) => {
    const type = text(span, "type");
    const children: { path: AddressLeaf["path"]; node: JsonWireNode; owner: JsonWireNode | null }[] = type === "link" || type === "bound_link"
      ? items(at(span, "content")).map((child, childIndex) => ({ path: [index, childIndex], node: child, owner: span }))
      : [{ path: [index], node: span, owner: null }];
    for (const child of children) {
      const size = text(child.node, "text").length;
      result.push({ path: child.path, span: child.node, owner: child.owner, start: cursor, end: cursor + size });
      cursor += size;
    }
  });
  return result;
}

export function contentText(content: JsonWireNode): string { return addressLeaves(content).map(leaf => text(leaf.span, "text")).join(""); }

export function leafReference(leaf: AddressLeaf): SpanRef {
  const span = leaf.span, type = text(span, "type");
  if (type === "fact_field") return { kind: "field", bindingId: text(span, "bindingId"), occurrenceId: text(span, "occurrenceId"),
    recordId: text(span, "recordId"), fieldKey: text(span, "fieldKey"), cellId: optionalText(span, "cellId") };
  if (type === "manual_scope") return { kind: "manual_scope", scopeId: text(span, "scopeId"),
    occurrenceId: text(span, "occurrenceId"), fragmentId: text(span, "fragmentId") };
  if (leaf.owner && text(leaf.owner, "type") === "bound_link") {
    const label = at(leaf.owner, "labelBinding"), binding = label.value === null ? at(leaf.owner, "urlBinding") : label;
    const [outer, inner] = leaf.path;
    return { kind: "bound_text", path: [outer, inner ?? invalid()], binding: label.value === null ? "url" : "label",
      recordId: text(binding, "recordId"), fieldKey: text(binding, "fieldKey"), cellId: text(binding, "cellId"),
      occurrenceId: text(binding, "occurrenceId") };
  }
  return { kind: "literal", path: leaf.path };
}

function identity(leaf: AddressLeaf): string | null {
  const type = text(leaf.span, "type");
  return type === "fact_field" ? `field:${text(leaf.span, "bindingId")}` : type === "manual_scope" ? `scope:${text(leaf.span, "fragmentId")}` : null;
}

function leafWire(leaf: AddressLeaf): string {
  const owner = leaf.owner ? jsonObjectWire([...leaf.owner.children].filter(([key]) => key !== "content").map(([key, child]) => {
    if (typeof key !== "string") return invalid();
    return [key, child.wire] as const;
  })) : "null";
  return `${leaf.span.wire}|${owner}`;
}

function containerKey(ref: ContainerRef): string {
  return JSON.stringify([ref.kind, ref.blockId, ref.kind === "cell" ? ref.cellId : null]);
}

export function locateContainer(index: Map<string, AddressBlock>, ref: ContainerRef): JsonWireNode {
  const block = index.get(ref.blockId);
  const group = block?.groups.find(value => value.kind === ref.kind && (ref.kind !== "cell" || value.key === ref.cellId));
  if (!block || !group || block.revision !== ref.revision || (ref.kind === "cell") !== (group.cellRevision !== null)
    || ref.kind === "cell" && group.cellRevision !== ref.cellRevision) return invalid();
  return group.content;
}

/** Structural invariants mirror the Pydantic model; they carry no domain rule. */
function coherent(map: PreparedAddressMapV1): void {
  if (map.baseSnapshot.projectId !== map.resultSnapshot.projectId || map.baseSnapshot.packageHash !== map.resultSnapshot.packageHash
    || canonicalValue(map.baseSnapshot) === canonicalValue(map.resultSnapshot) && map.containers.length) invalid();
  const pairs = new Set<string>(), outputs = new Map<string, AddressContainer[]>(), inputs = new Map<string, AddressContainer[]>();
  const created = new Map<string, string>();
  for (const entry of map.containers) {
    const pair = JSON.stringify([entry.input ? containerKey(entry.input) : null, containerKey(entry.output)]);
    if (pairs.has(pair)) invalid();
    pairs.add(pair);
    if (entry.created) {
      const slot = JSON.stringify([entry.created.opId, entry.created.slot]);
      if ((created.get(slot) ?? entry.output.blockId) !== entry.output.blockId) invalid();
      created.set(slot, entry.output.blockId);
    }
    outputs.set(containerKey(entry.output), [...outputs.get(containerKey(entry.output)) ?? [], entry]);
    if (entry.input) inputs.set(containerKey(entry.input), [...inputs.get(containerKey(entry.input)) ?? [], entry]);
    const sourced = entry.input !== null;
    if (sourced !== (entry.beforeContentHash !== null) || sourced !== (entry.beforeLength !== null)
      || entry.input && entry.input.kind !== entry.output.kind) invalid();
    if (entry.correspondence === "none") {
      if (entry.regions.length || entry.segments.length || entry.boundaries.length) invalid();
      continue;
    }
    let previous: AddressContainer["regions"][number] | null = null;
    for (const region of entry.regions) {
      if ((region.role === "inserted") !== (region.source === null) || region.result.end < region.result.start
        || region.result.end > entry.afterLength || region.source && (region.source.end < region.source.start
          || region.source.end - region.source.start !== region.result.end - region.result.start
          || entry.beforeLength === null || region.source.end > entry.beforeLength)
        || previous && (region.result.start !== previous.result.end
          || region.source && previous.source && region.source.start < previous.source.end)) invalid();
      previous = region;
    }
    const edges = new Set<number>();
    let position = -1;
    for (const segment of entry.segments) {
      const { result, source } = segment;
      if (result.end < result.start || result.start < position || (segment.role === "inserted") !== (source === null)) invalid();
      position = result.start;
      const region = entry.regions.find(value => value.role === segment.role
        && value.result.start <= result.start && result.end <= value.result.end);
      if (!region) invalid();
      if (source) {
        const shift = (region.source?.start ?? invalid()) - region.result.start;
        if (source.start !== result.start + shift || source.end !== result.end + shift) invalid();
      }
      edges.add(result.start); edges.add(result.end);
    }
    const offsets = entry.boundaries.map(value => value.offset);
    if (canonicalValue(offsets) !== canonicalValue([...edges].sort((a, b) => a - b))) invalid();
  }
  for (const group of inputs.values()) {
    const first = group[0] ?? invalid();
    if (group.some(value => canonicalValue([value.input, value.beforeContentHash, value.beforeLength])
      !== canonicalValue([first.input, first.beforeContentHash, first.beforeLength]))) invalid();
  }
  for (const group of outputs.values()) {
    const first = group[0] ?? invalid();
    if (group.some(value => canonicalValue([value.output, value.created, value.afterContentHash, value.afterLength, value.correspondence])
      !== canonicalValue([first.output, first.created, first.afterContentHash, first.afterLength, first.correspondence]))) invalid();
    if (first.correspondence !== "exact") continue;
    const regions = group.flatMap(value => value.regions.map(region => [region.result.start, region.result.end] as const))
      .sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let cursor = 0;
    for (const [start, end] of regions) {
      if (start !== cursor) invalid();
      cursor = end;
    }
    if (cursor !== first.afterLength) invalid();
  }
}

type Piece = { start: number; end: number };

/** Mechanical address of one leaf; Python decides validity, so null is always accepted. */
export function leafTarget(leaf: AddressLeaf): AddressTarget | null {
  const type = text(leaf.span, "type");
  if (type === "fact_field") return at(leaf.span, "complete").value === true ? { kind: "field", bindingId: text(leaf.span, "bindingId") } : null;
  if (type === "manual_scope") return { kind: "manual_scope", fragmentId: text(leaf.span, "fragmentId") };
  return leaf.owner && text(leaf.owner, "type") === "bound_link" ? null : { kind: "literal" };
}

function claims(value: AddressTarget | null, allowed: AddressTarget | null): boolean {
  return value === null || allowed !== null && canonicalValue(value) === canonicalValue(allowed);
}

function boundaryClaims(boundary: AddressContainer["boundaries"][number], outputLeaves: readonly AddressLeaf[], length: number): boolean {
  const offset = boundary.offset, nonempty = outputLeaves.filter(leaf => leaf.end > leaf.start);
  const inside = nonempty.find(leaf => leaf.start < offset && offset < leaf.end);
  if (inside) return claims(boundary.before, leafTarget(inside)) && claims(boundary.after, leafTarget(inside));
  const left = nonempty.find(leaf => leaf.end === offset), right = nonempty.find(leaf => leaf.start === offset);
  const before = offset === 0 ? { kind: "literal" as const } : left ? leafTarget(left) : null;
  const after = offset === length ? { kind: "literal" as const } : right ? leafTarget(right) : null;
  return claims(boundary.before, before) && claims(boundary.after, after);
}

async function verifyOutput(group: readonly AddressContainer[], before: Map<string, AddressBlock>, after: Map<string, AddressBlock>,
  createdIds: AddressExpectation["createdIds"], allocated: ReadonlySet<string>): Promise<boolean> {
  const first = group[0];
  if (!first) return false;
  const output = locateContainer(after, first.output), outputLeaves = addressLeaves(output), outputText = contentText(output);
  if (await sha256(output.wire) !== first.afterContentHash || outputText.length !== first.afterLength) return false;
  const fresh = !before.has(first.output.blockId);
  if (fresh !== (first.created !== null) || first.created
    && createdIds[first.created.opId]?.[first.created.slot] !== first.output.blockId) return false;
  const inputs: AddressLeaf[][] = [], texts: string[] = [];
  for (const entry of group) {
    if (!entry.input) { inputs.push([]); texts.push(""); continue; }
    const input = locateContainer(before, entry.input);
    inputs.push(addressLeaves(input)); texts.push(contentText(input));
    if (await sha256(input.wire) !== entry.beforeContentHash || texts.at(-1)?.length !== entry.beforeLength) return false;
  }
  if (first.correspondence === "none") return true;
  const pieces = new Map<AddressLeaf, Piece[]>();
  for (const [index, entry] of group.entries()) {
    const inputLeaves = inputs[index] ?? [], inputText = texts[index] ?? "";
    for (const region of entry.regions) {
      if (region.source && inputText.slice(region.source.start, region.source.end)
        !== outputText.slice(region.result.start, region.result.end)) return false;
    }
    for (const segment of entry.segments) {
      const { result, source } = segment, wanted = canonicalValue(result.span);
      const leaf = outputLeaves.find(value => value.start <= result.start && result.end <= value.end
        && (result.end > result.start) === (value.end > value.start) && canonicalValue(leafReference(value)) === wanted);
      if (!leaf || !claims(segment.target, leafTarget(leaf))) return false;
      pieces.set(leaf, [...pieces.get(leaf) ?? [], { start: result.start, end: result.end }]);
      if (source && !inputLeaves.some(value => value.start <= source.start && source.end <= value.end
        && (source.end > source.start) === (value.end > value.start)
        && canonicalValue(leafReference(value)) === canonicalValue(source.span))) return false;
      const identifier = result.span.kind === "field" ? result.span.bindingId
        : result.span.kind === "manual_scope" ? result.span.fragmentId : null;
      const slot = segment.slot;
      if ((slot !== null) !== (identifier !== null && allocated.has(identifier))
        || slot && createdIds[slot.opId]?.[slot.slot] !== identifier) return false;
    }
    if (!entry.boundaries.every(boundary => boundaryClaims(boundary, outputLeaves, outputText.length))) return false;
  }
  const regions = group.flatMap((entry, index) => entry.regions.map(region => ({ region, index })));
  for (const leaf of outputLeaves) {
    const listed = (pieces.get(leaf) ?? []).sort((a, b) => a.start - b.start);
    if (listed.length) {
      // Listed pieces must tile the whole leaf; a partial list would hide a changed remainder.
      if (leaf.start === leaf.end ? listed.length !== 1 : listed.some((piece, position) =>
        piece.start !== (position ? listed[position - 1]?.end : leaf.start)) || listed.at(-1)?.end !== leaf.end) return false;
      continue;
    }
    const key = identity(leaf);
    if (leaf.start === leaf.end) {
      if (key === null) return false;
      const matched = regions.some(({ region, index }) => region.source && (inputs[index] ?? []).some(value =>
        identity(value) === key && leafWire(value) === leafWire(leaf)
        && value.start >= region.source!.start && value.start <= region.source!.end
        && leaf.start === region.result.start + value.start - region.source!.start));
      if (!matched) return false;
      continue;
    }
    const owner = regions.filter(({ region }) => region.result.start <= leaf.start && leaf.end <= region.result.end);
    const [found] = owner;
    if (owner.length !== 1 || !found || !found.region.source) return false;
    const shift = found.region.source.start - found.region.result.start;
    if (!(inputs[found.index] ?? []).some(value => value.start === leaf.start + shift && value.end === leaf.end + shift
      && leafWire(value) === leafWire(leaf))) return false;
  }
  return true;
}

/** Verify a server address map against the exact retained base and verified result responses. */
export async function verifyAddressMap(mapInput: JsonWireNode, mapSha256: string, baseInput: JsonWireNode,
  resultInput: JsonWireNode, expected: AddressExpectation): Promise<VerifiedAddressMap> {
  // Own the decoded trees before awaiting so later mutations cannot change verified values.
  const root = parseJsonWire(mapInput.wire), base = parseJsonWire(baseInput.wire), result = parseJsonWire(resultInput.wire);
  const createdIds = structuredClone(expected.createdIds);
  const map = root.value;
  if (!mapShape(map) || map.clientMutationId !== expected.clientMutationId || map.requestHash !== expected.requestHash
    || at(root, "baseSnapshot").wire !== at(base, "snapshot").wire
    || at(root, "resultSnapshot").wire !== at(result, "snapshot").wire) return invalid();
  coherent(map);
  if (await sha256(root.wire) !== mapSha256) return invalid();
  const before = responseBlocks(base), after = responseBlocks(result);
  const allocated = new Set(Object.values(createdIds).flatMap(slots => Object.values(slots)));
  const listed = new Set(map.containers.map(entry => containerKey(entry.output)));
  // Every changed or new container must be mapped; equal content is an unchanged preimage.
  for (const [id, block] of after) for (const group of block.groups) {
    const previous = before.get(id)?.groups.find(value => value.kind === group.kind && value.key === group.key);
    const ref: ContainerRef = group.kind === "cell"
      ? { kind: "cell", blockId: id, revision: block.revision, cellId: group.key, cellRevision: group.cellRevision ?? invalid() }
      : { kind: group.kind, blockId: id, revision: block.revision };
    if (listed.has(containerKey(ref)) !== (previous?.content.wire !== group.content.wire)) return invalid();
  }
  const outputs = new Map<string, AddressContainer[]>();
  for (const entry of map.containers) outputs.set(containerKey(entry.output), [...outputs.get(containerKey(entry.output)) ?? [], entry]);
  for (const group of outputs.values()) {
    if (!await verifyOutput(group, before, after, createdIds, allocated)) return invalid();
  }
  return { map, wire: root.wire, sha256: mapSha256 };
}
