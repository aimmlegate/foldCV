import { parseJsonWire, type JsonWireNode } from "./lossless-json";

const wires = new WeakMap<object, string>();

function sameJsonValue(expected: unknown, actual: unknown, ancestors = new WeakSet<object>()): boolean {
  if (typeof actual === "number" && !Number.isFinite(actual)) return false;
  if (typeof expected !== "object" || expected === null) return Object.is(expected, actual);
  if (typeof actual !== "object" || actual === null || ancestors.has(actual)) return false;
  if (Array.isArray(expected) !== Array.isArray(actual) || Object.getOwnPropertySymbols(actual).length) return false;
  if (!Array.isArray(actual) && Object.getPrototypeOf(actual) !== Object.prototype && Object.getPrototypeOf(actual) !== null) return false;
  const keys = Object.keys(expected);
  if (keys.length !== Object.keys(actual).length || Array.isArray(expected) && Array.isArray(actual) && expected.length !== actual.length) return false;
  ancestors.add(actual);
  const result = keys.every(key => Object.hasOwn(actual, key) && sameJsonValue(Reflect.get(expected, key), Reflect.get(actual, key), ancestors));
  ancestors.delete(actual);
  return result;
}

export function decodeJsonResponse(source: string): unknown {
  const root = parseJsonWire(source);
  if (typeof root.value === "object" && root.value !== null) wires.set(root.value, root.wire);
  return root.value;
}

/** Never reuse hash evidence after a caller changes the decoded object. */
export function jsonResponseWire(value: unknown): JsonWireNode {
  const wire = typeof value === "object" && value !== null ? wires.get(value) : undefined;
  if (wire === undefined) throw new Error("INVALID_RESULT");
  const root = parseJsonWire(wire);
  if (!sameJsonValue(root.value, value)) throw new Error("INVALID_RESULT");
  if (typeof root.value === "object" && root.value !== null) wires.set(root.value, root.wire);
  return root;
}
