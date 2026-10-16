export async function sha256(wire: string | Uint8Array<ArrayBuffer>): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", typeof wire === "string" ? new TextEncoder().encode(wire) : wire);
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}

function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (typeof value === "object" && value !== null) return Object.fromEntries(Object.entries(value)
    .sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, ordered(item)]));
  return value;
}

export function sameValue(a: unknown, b: unknown): boolean { return JSON.stringify(ordered(a)) === JSON.stringify(ordered(b)); }

export function containsSubmitted(submitted: unknown, echoed: unknown): boolean {
  if (Array.isArray(submitted)) return Array.isArray(echoed) && submitted.length === echoed.length
    && submitted.every((item: unknown, index) => containsSubmitted(item, echoed[index]));
  if (typeof submitted === "object" && submitted !== null) {
    if (typeof echoed !== "object" || echoed === null || Array.isArray(echoed)) return false;
    const values = echoed as Record<string, unknown>;
    return Object.entries(submitted).every(([key, item]) => key in values && containsSubmitted(item, values[key]));
  }
  return submitted === echoed;
}
