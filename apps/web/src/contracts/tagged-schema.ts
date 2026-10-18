const prepared = new WeakMap<object, object>();

export function taggedSchema(schema: object): object {
  const existing = prepared.get(schema);
  if (existing) return existing;
  const visit = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(visit);
    if (typeof value !== "object" || value === null) return value;
    const result = Object.fromEntries(Object.entries(value).map(([key, child]) => [key, visit(child)]));
    const discriminator: unknown = result["discriminator"];
    if (typeof discriminator === "object" && discriminator !== null) {
      // Ajv derives tags from each branch's const/enum and rejects OpenAPI mappings.
      result["discriminator"] = Object.fromEntries(Object.entries(discriminator).filter(([key]) => key !== "mapping"));
    }
    return result;
  };
  const result = visit(schema);
  if (typeof result !== "object" || result === null || Array.isArray(result)) throw new Error("Invalid schema root");
  prepared.set(schema, result);
  return result;
}
