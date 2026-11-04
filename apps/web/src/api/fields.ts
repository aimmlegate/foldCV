import { ProjectApiFailure } from "../rich/v7-connection";

/** Readers of hand-parsed replies: a missing or mistyped field is an INVALID_RESULT. */
export function field(value: unknown, key: string): unknown {
  return typeof value === "object" && value !== null ? Reflect.get(value, key) : undefined;
}
export function text(value: unknown, key: string): string {
  const item = field(value, key);
  if (typeof item !== "string") throw new ProjectApiFailure("INVALID_RESULT");
  return item;
}
export function optionalText(value: unknown, key: string): string | null {
  const item = field(value, key);
  if (item !== null && typeof item !== "string") throw new ProjectApiFailure("INVALID_RESULT");
  return item;
}
