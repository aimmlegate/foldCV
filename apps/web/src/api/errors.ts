/** The public code of a JSON error reply (`{"error": {"code": …}}`); REQUEST_FAILED for any other value. */
export function errorCodeOf(value: unknown): string {
  if (typeof value !== "object" || value === null || !("error" in value)) return "REQUEST_FAILED";
  const error = value.error;
  return typeof error === "object" && error !== null && "code" in error && typeof error.code === "string"
    ? error.code : "REQUEST_FAILED";
}
