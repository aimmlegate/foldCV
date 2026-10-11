import assert from "node:assert/strict";
import test from "node:test";
import sheetFixture from "../../../contracts/examples/fact_sheet.json" with { type: "json" };
import type { FactSheet } from "../src/contracts/generated/fact_sheet";
import { validateFactSheet } from "../src/contracts/validate";
import { mergeDraftSheet } from "../src/facts/draftWorkflow";

test("explicit job correction is selected as user text without replacing source evidence", () => {
  const source: unknown = structuredClone(sheetFixture);
  assert.ok(validateFactSheet(source));
  const normalized = source as FactSheet;
  const unit = normalized.units[0]!;
  const sourceFact: FactSheet["facts"][number] = { id: "fact_source_job", revision: 1, kind: "text",
    value: { text: "Old job wording" }, evidence: [{ sourceId: unit.sourceId, sourceRevision: 1,
      unitId: unit.unitId, unitRevision: 1 }], origin: "source", importance: "normal",
    jobId: "job_source", subprojectId: null };
  normalized.facts.push(sourceFact);
  unit.factIds.push(sourceFact.id);
  unit.disposition = "facts";
  normalized.employment = [{ id: "job_source", employer: "Example Works", role: "Developer",
    periods: [{ start: { precision: "year", year: 2022, month: null, day: null },
      end: { precision: "year", year: 2025, month: null, day: null } }], sourceId: unit.sourceId,
    unitIds: [unit.unitId], subprojects: [], factIds: [sourceFact.id], reviewRequired: true }];
  assert.ok(validateFactSheet(normalized));
  const accepted = structuredClone(normalized);
  accepted.facts.push({ id: "fact_user_fix", revision: 1, kind: "text",
    value: { text: "Corrected job wording" }, evidence: [], origin: "user", importance: "normal",
    jobId: null, subprojectId: null });
  accepted.userCorrections = { fact_source_job: "fact_user_fix" };
  assert.ok(validateFactSheet(accepted));
  const merged = mergeDraftSheet(normalized, accepted);
  const correction = merged.facts.find((fact) => fact.id === "fact_user_fix");
  assert.equal(correction?.jobId, "job_source");
  assert.equal(correction?.origin, "user");
  assert.deepEqual(correction?.evidence, []);
  assert.ok(merged.employment?.[0]?.factIds.includes("fact_user_fix"));
  assert.ok(merged.facts.some((fact) => fact.id === sourceFact.id));
  assert.deepEqual(accepted.facts.find((fact) => fact.id === "fact_user_fix")?.jobId, null);

  const otherUnit = normalized.units[1]!;
  const other: typeof sourceFact = { ...structuredClone(sourceFact), id: "fact_source_other", jobId: "job_other",
    evidence: [{ sourceId: otherUnit.sourceId, sourceRevision: 1, unitId: otherUnit.unitId, unitRevision: 1 }] };
  normalized.facts.push(other);
  otherUnit.factIds.push(other.id);
  otherUnit.disposition = "facts";
  normalized.employment?.push({ ...structuredClone(normalized.employment[0]!), id: "job_other", unitIds: [otherUnit.unitId],
    factIds: [other.id] });
  accepted.facts.push(structuredClone(other));
  accepted.units[1]!.factIds.push(other.id);
  accepted.units[1]!.disposition = "facts";
  accepted.employment?.push(structuredClone(normalized.employment![1]!));
  accepted.userCorrections = { fact_source_job: "fact_user_fix", fact_source_other: "fact_user_fix" };
  assert.ok(validateFactSheet(normalized), "normalized sheet remains valid");
  assert.ok(validateFactSheet(accepted), "accepted sheet remains valid");
  const ambiguous = mergeDraftSheet(normalized, accepted);
  assert.equal(ambiguous.facts.find((fact) => fact.id === "fact_user_fix")?.jobId, null);
});
