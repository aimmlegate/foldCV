import type { CellChange } from "./history";

export type DateAnchor = { jobId: string; periodId: string; actionId: string };
export function dateAnchors(actionId: string, changes: CellChange[]): DateAnchor[] {
  const result = new Map<string, DateAnchor>();
  for (const change of changes) {
    if (!change.key.startsWith("fact-field:")) continue;
    const pair: unknown = JSON.parse(change.key.slice(11));
    if (!Array.isArray(pair) || typeof pair[0] !== "string" || typeof pair[1] !== "string" || !pair[1].startsWith("period:")) continue;
    const periodId = pair[1].slice(7, pair[1].lastIndexOf(":"));
    const payload = (value: string | null): string => {
      const field: unknown = value ? JSON.parse(value) : null;
      return typeof field === "object" && field !== null && "rawText" in field && "value" in field
        ? JSON.stringify([field.rawText, field.value]) : "null";
    };
    if (payload(change.before) !== payload(change.after)) result.set(periodId, { jobId: pair[0], periodId, actionId });
  }
  return [...result.values()];
}
