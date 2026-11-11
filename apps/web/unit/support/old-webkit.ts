const upsert = ["getOrInsert", "getOrInsertComputed"];
const arrayIterator = Reflect.getPrototypeOf([][Symbol.iterator]()), iterator = arrayIterator && Reflect.getPrototypeOf(arrayIterator);
// Built-ins that came after Safari 16.4, the oldest WebKit the PDF original is kept working on.
const newer: [object | null, string[]][] = [
  [Promise, ["withResolvers", "try"]], [ArrayBuffer.prototype, ["transfer", "transferToFixedLength", "detached"]],
  [Object, ["groupBy"]], [Map, ["groupBy"]], [Map.prototype, upsert], [WeakMap.prototype, upsert],
  [Set.prototype, ["union", "intersection", "difference", "symmetricDifference", "isSubsetOf", "isSupersetOf", "isDisjointFrom"]],
  [Math, ["sumPrecise", "f16round"]], [URL, ["parse", "canParse"]], [AbortSignal, ["any"]], [RegExp, ["escape"]], [Error, ["isError"]],
  [Uint8Array, ["fromBase64", "fromHex"]], [Uint8Array.prototype, ["toBase64", "toHex", "setFromBase64", "setFromHex"]],
  [iterator, ["map", "filter", "take", "drop", "flatMap", "reduce", "toArray", "forEach", "some", "every", "find"]],
  [globalThis, ["Iterator", "Float16Array"]],
];

/** Leaves this process with the JavaScript of Safari 16.4. A test file runs in its own process, so nothing else sees it. */
export function removeNewerJavaScript(): void {
  for (const [target, names] of newer) for (const name of names) if (target) Reflect.deleteProperty(target, name);
}

/** Calls a method the TypeScript library of this project does not know yet. */
export function call(target: object, name: string, ...values: unknown[]): unknown {
  const method: unknown = Reflect.get(target, name);
  if (typeof method !== "function") throw new TypeError(`${name} is missing`);
  return Reflect.apply(method, target, values);
}
