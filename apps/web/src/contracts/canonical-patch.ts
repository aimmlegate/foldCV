import { sha256 } from "../background/wire";
import type { CanonicalPatchV1 } from "./generated/canonical_patch_v1";
import { jsonObjectWire, parseJsonWire, type JsonWireNode } from "./lossless-json";

export type CanonicalPatchStep = CanonicalPatchV1["steps"][number];

type Node = {
  data: JsonWireNode;
  children: Map<string | number, Node>;
  original: ReadonlyMap<Node, number>;
};

function invalid(): never { throw new Error("INVALID_RESULT"); }

function track(data: JsonWireNode): Node {
  const children = new Map([...data.children].map(([key, child]) => [key, track(child)]));
  return { data, children, original: new Map([...children.values()].map((child, index) => [child, index])) };
}

function pointer(source: string): string[] {
  if (!source.startsWith("/") || /~(?:[^01]|$)/.test(source)) return invalid();
  return source.slice(1).split("/").map(part => part.replaceAll("~1", "/").replaceAll("~0", "~"));
}

function arrayIndex(parent: Node, key: string, insert = false): string | number {
  if (Array.isArray(parent.data.value)) {
    if (!/^(?:0|[1-9][0-9]*)$/.test(key)) return invalid();
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index >= parent.children.size + Number(insert)) return invalid();
    return index;
  }
  if (parent.data.value === null || typeof parent.data.value !== "object") return invalid();
  return key;
}

function output(node: Node): JsonWireNode {
  if (Array.isArray(node.data.value)) {
    const children = new Map([...node.children.values()].map((child, index) => [index, output(child)]));
    return { value: [...children.values()].map(child => child.value), children,
      wire: `[${[...children.values()].map(child => child.wire).join(",")}]` };
  }
  if (node.data.value !== null && typeof node.data.value === "object") {
    const entries = [...node.children].map(([key, child]) => {
      if (typeof key !== "string") return invalid();
      return [key, output(child)] as const;
    });
    return { value: Object.fromEntries(entries.map(([key, child]) => [key, child.value])), children: new Map(entries),
      wire: jsonObjectWire(entries.map(([key, child]) => [key, child.wire])) };
  }
  return node.data;
}

function textBoundary(text: string, offset: number): boolean {
  if (!Number.isSafeInteger(offset) || offset < 0 || offset > text.length) return false;
  const left = text.charCodeAt(offset - 1), right = text.charCodeAt(offset);
  return !(left >= 0xd800 && left <= 0xdbff && right >= 0xdc00 && right <= 0xdfff);
}

/** Numeric tokens stay in JsonWireNode.wire until the exact result hash is checked. */
export async function applyCanonicalPatch(base: JsonWireNode, steps: readonly CanonicalPatchStep[]): Promise<JsonWireNode> {
  if (steps.length > 1000) return invalid();
  const root = track(base), changed = new Set<Node>(), descendants = new Set<Node>();
  const arrays = new Map<Node, readonly [number, number]>();
  function phase(node: Node, number: number, index: number): void {
    const previous = arrays.get(node);
    if (previous && (number < previous[0] || number === previous[0]
      && (number === 0 ? index < previous[1] : number === 1 ? index >= previous[1] : index <= previous[1]))) invalid();
    arrays.set(node, [number, index]);
  }
  function original(node: Node, child: Node): number {
    const index = node.original.get(child);
    return index === undefined ? invalid() : index;
  }
  for (const step of steps) {
    const path = pointer(step.pointer), ancestors: Node[] = [];
    let node = root;
    for (const part of path.slice(0, -1)) {
      if (changed.has(node)) return invalid();
      ancestors.push(node);
      const key = arrayIndex(node, part), child = node.children.get(key);
      if (!child || changed.has(child)) return invalid();
      if (Array.isArray(node.data.value)) phase(node, 0, original(node, child));
      node = child;
    }
    if (changed.has(node)) return invalid();
    ancestors.push(node);
    const last = path.at(-1);
    if (last === undefined) return invalid();
    const key = arrayIndex(node, last, step.kind === "insert"), target = node.children.get(key);
    if (step.kind === "insert") {
      if (typeof key !== "number") return invalid();
      phase(node, 2, key);
    } else {
      if (!target && step.kind !== "set") return invalid();
      if (target && (changed.has(target) || descendants.has(target))) return invalid();
      if (Array.isArray(node.data.value)) {
        if (!target) return invalid();
        phase(node, step.kind === "remove" ? 1 : 0, original(node, target));
      }
    }
    let replacement: Node | undefined;
    if (step.kind === "set" || step.kind === "insert") {
      const parsed = parseJsonWire(step.valueWire);
      if (parsed.wire !== step.valueWire) return invalid();
      replacement = track(parsed);
    } else if (step.kind === "splice_text") {
      const text = target?.data.value;
      if (typeof text !== "string" || await sha256(text) !== step.beforeTextHash
        || !textBoundary(text, step.start) || !textBoundary(text, step.end) || step.start > step.end) return invalid();
      replacement = track(parseJsonWire(JSON.stringify(text.slice(0, step.start) + step.text + text.slice(step.end))));
    }
    if (typeof key === "number") {
      const list = [...node.children.values()];
      if (step.kind === "remove") list.splice(key, 1);
      else if (!replacement) return invalid();
      else if (step.kind === "insert") list.splice(key, 0, replacement);
      else list[key] = replacement;
      node.children = new Map(list.map((child, index) => [index, child]));
    } else if (step.kind === "remove") node.children.delete(key);
    else if (replacement) node.children.set(key, replacement);
    else return invalid();
    if (target && step.kind !== "insert") changed.add(target);
    if (replacement) changed.add(replacement);
    ancestors.forEach(ancestor => descendants.add(ancestor));
  }
  return output(root);
}

export async function applyVerifiedCanonicalPatch(base: JsonWireNode, steps: readonly CanonicalPatchStep[],
  beforeHash: string, afterHash: string): Promise<JsonWireNode> {
  if (await sha256(base.wire) !== beforeHash) return invalid();
  const result = await applyCanonicalPatch(base, steps);
  if (await sha256(result.wire) !== afterHash) return invalid();
  return result;
}
