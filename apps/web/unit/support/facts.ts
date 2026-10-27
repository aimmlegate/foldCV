import type { WorkingFacts } from "../../src/contracts/generated/working_facts";

/** Minimal synthetic facts for the facts panel helpers; no project file is read. */
type Records = WorkingFacts["records"][number];
export type Employment = Extract<Records, { kind: "employment" }>;
export type Technology = Extract<Records, { kind: "technology" }>;

export const known = (rawText: string) => ({ value: rawText, rawText, status: "known" as const, revision: 1, pendingRawText: null });

export function employment(id: string, employer = "Example Company", role = "Engineer"): Employment {
  const month = (year: number, value: number) => ({ value: { precision: "month" as const, year, month: value, day: null },
    rawText: `${year}-${String(value).padStart(2, "0")}`, status: "known" as const, revision: 1, pendingRawText: null });
  return { id, revision: 1, origin: "user", evidence: [], kind: "employment", employer: known(employer), role: known(role),
    periods: [{ id: `${id}-period`, revision: 1, evidence: [], start: month(2024, 1), end: month(2024, 4),
      present: { value: false, rawText: "", status: "known", revision: 1, pendingRawText: null } }] };
}

export function technology(id: string, display: string, jobId: string | null = null): Technology {
  return { id, revision: 1, kind: "technology", origin: "user", evidence: [], userCorrected: true, jobId, subprojectId: null,
    display: known(display), canonicalId: { value: null, rawText: "", status: "unknown", revision: 1, pendingRawText: null } };
}

export function facts(records: Records[] = [employment("job-1")]): WorkingFacts {
  return { revision: 1, records, tombstones: [] };
}
