export type JsonWireNode = {
  readonly value: unknown;
  readonly wire: string;
  readonly children: ReadonlyMap<string | number, JsonWireNode>;
};

function codePointOrder(left: string, right: string): number {
  const a = [...left], b = [...right];
  for (let index = 0; index < Math.min(a.length, b.length); index++) {
    const difference = (a[index]?.codePointAt(0) ?? 0) - (b[index]?.codePointAt(0) ?? 0);
    if (difference) return difference;
  }
  return a.length - b.length;
}

export function jsonObjectWire(entries: readonly (readonly [string, string])[]): string {
  if (new Set(entries.map(([key]) => key)).size !== entries.length) throw new Error("INVALID_RESULT");
  return `{${[...entries].sort(([a], [b]) => codePointOrder(a, b))
    .map(([key, wire]) => `${JSON.stringify(key)}:${wire}`).join(",")}}`;
}

/** Numeric lexemes must survive until the Python snapshot hashes are checked. */
export function parseJsonWire(source: string): JsonWireNode {
  let cursor = 0;
  const invalid = (): never => { throw new Error("INVALID_RESULT"); };
  function whitespace(): void { while (/[ \t\r\n]/.test(source[cursor] ?? "")) cursor++; }
  function string(): string {
    // A scan, not a repeated regex group: one backtrack entry per character overflowed on the 11 MB workspace wire.
    if (source[cursor] !== '"') return invalid();
    let end = cursor + 1;
    for (let code = source.charCodeAt(end); code !== 0x22; code = source.charCodeAt(end)) {
      if (Number.isNaN(code) || code < 0x20) return invalid();
      if (code !== 0x5c) { end++; continue; }
      const escape = source[end + 1] ?? "";
      if (escape === "u" && /^[0-9a-fA-F]{4}$/.test(source.slice(end + 2, end + 6))) end += 6;
      else if (escape !== "" && '"\\/bfnrt'.includes(escape)) end += 2;
      else return invalid();
    }
    const value: unknown = JSON.parse(source.slice(cursor, end + 1));
    cursor = end + 1;
    if (typeof value !== "string" || /\p{Cs}/u.test(value)) return invalid();
    return value;
  }
  function parse(): JsonWireNode {
    whitespace();
    const children = new Map<string | number, JsonWireNode>();
    if (source[cursor] === "{") {
      cursor++; whitespace();
      if (source[cursor] !== "}") while (true) {
        whitespace(); const key = string(); whitespace();
        if (children.has(key) || source[cursor++] !== ":") return invalid();
        children.set(key, parse()); whitespace();
        if (source[cursor] === "}") break;
        if (source[cursor++] !== ",") return invalid();
      }
      cursor++;
      const keys = [...children.keys()].filter((key): key is string => typeof key === "string").sort(codePointOrder);
      const entries = keys.map(key => {
        const child = children.get(key); if (!child) return invalid();
        return [key, child] as const;
      });
      return { value: Object.fromEntries(entries.map(([key, child]) => [key, child.value])), children,
        wire: `{${entries.map(([key, child]) => `${JSON.stringify(key)}:${child.wire}`).join(",")}}` };
    }
    if (source[cursor] === "[") {
      cursor++; whitespace(); let index = 0;
      if (source[cursor] !== "]") while (true) {
        children.set(index++, parse()); whitespace();
        if (source[cursor] === "]") break;
        if (source[cursor++] !== ",") return invalid();
      }
      cursor++;
      return { value: [...children.values()].map(child => child.value), children,
        wire: `[${[...children.values()].map(child => child.wire).join(",")}]` };
    }
    if (source[cursor] === '"') {
      const value = string();
      return { value, wire: JSON.stringify(value), children };
    }
    for (const token of ["true", "false", "null"] as const) if (source.startsWith(token, cursor)) {
      cursor += token.length;
      return { value: token === "true" ? true : token === "false" ? false : null, wire: token, children };
    }
    const match = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(source.slice(cursor));
    if (!match) return invalid();
    const value: unknown = JSON.parse(match[0]);
    if (typeof value !== "number" || !Number.isFinite(value)) return invalid();
    cursor += match[0].length;
    return { value, wire: match[0], children };
  }
  const root = parse(); whitespace();
  if (cursor !== source.length) return invalid();
  return root;
}

export function jsonWireAt(root: JsonWireNode, path: readonly (string | number)[]): JsonWireNode {
  let current = root;
  for (const key of path) {
    const next = current.children.get(key);
    if (!next) throw new Error("INVALID_RESULT");
    current = next;
  }
  return current;
}
