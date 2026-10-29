import type { Preferences } from "../contracts/generated/preferences";

export type ReasoningEffort = NonNullable<Preferences["rewriteReasoningEffort"]>;
export type ModelReasoning = { supported: ReasoningEffort[]; default: ReasoningEffort | null };
const efforts: readonly string[] = ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"];
export function isReasoningEffort(value: unknown): value is ReasoningEffort {
  return typeof value === "string" && efforts.includes(value);
}
/** "high" and above: an import at this level takes noticeably longer. */
export function longReasoning(value: ReasoningEffort): boolean {
  return efforts.indexOf(value) >= efforts.indexOf("high");
}
export function validReasoning(value: unknown, models: readonly unknown[]): value is Record<string, ModelReasoning> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  return Object.entries(value).every(([model, entry]: [string, unknown]) => {
    if (!models.includes(model) || typeof entry !== "object" || entry === null || !("supported" in entry) || !("default" in entry)) return false;
    return Array.isArray(entry.supported) && entry.supported.length <= 8 && entry.supported.every(isReasoningEffort)
      && new Set(entry.supported).size === entry.supported.length
      && (entry.default === null || isReasoningEffort(entry.default) && entry.supported.includes(entry.default));
  });
}
