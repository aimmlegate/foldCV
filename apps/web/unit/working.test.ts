import assert from "node:assert/strict";
import test from "node:test";
import sourceRequest from "../../../contracts/examples/fact_request.json" with { type: "json" };
import sheetFixture from "../../../contracts/examples/fact_sheet.json" with { type: "json" };
import type { ExtractResult } from "../src/contracts/generated/extract_result";
import type { FactSheet } from "../src/contracts/generated/fact_sheet";
import { validateContract, validateExtractResult, validateFactSheet } from "../src/contracts/validate";
import { adaptDraftedWorking, adaptWorking, type ManualInput, type WorkingDraft } from "../src/facts/working";
import { editorReducer, initialEditorState } from "../src/editor/state";

function working(): WorkingDraft {
  const result: unknown = structuredClone(sourceRequest.sources[0]?.result);
  const sheet: unknown = structuredClone(sheetFixture);
  assert.ok(validateExtractResult(result) && validateFactSheet(sheet));
  const imported = result as ExtractResult;
  const facts = sheet as FactSheet;
  const manual: ManualInput = { name: "Alex Example", title: "Engineer", asOf: "2026-10-11",
    education: "Example University", language: "en", languages: ["English"],
    skills: ["Python 3.11", "ObscureDB 2.0"],
    employment: [{ id: "job_user_1", employer: "Example Works", role: "Developer", start: "2020",
      end: "2025", description: "Built a source-safe tool.",
      subprojects: [{ id: "sub_user_1", name: "Local client", start: "2021", end: "2023",
        description: "Prepared local documents." }] }],
    metrics: [{ id: "metric_user_global", jobId: null, number: 10, upperNumber: null,
      comparator: "exact", unit: "systems", period: null, baseline: null, result: null,
      scope: null, attribution: "personal", qualifiers: [] },
      { id: "metric_user_1", jobId: "job_user_1", number: 20, upperNumber: null,
      comparator: "at_most", unit: "requests", period: "day", baseline: null, result: null,
      scope: "service", attribution: "team", qualifiers: ["peak"] }],
    leadership: [{ id: "lead_user_1", jobId: "job_user_1", action: "Built the team",
      attribution: "personal", teamSize: 5, teamUnit: "engineers", teamBaseline: "zero" }] };
  return { transportVersion: 1, sources: [{ entry: { result: imported, overlays: { "unit:unit_1": "User overlay" } },
    originalBytes: new Uint8Array(imported.byteLength).fill(42) }], sheet: facts, priorSheet: null,
    sourceReviewStale: false, manual, draft: null };
}

test("working transport keeps exact originals, full sheet and manual data beside v3 render adapter", () => {
  const input = working();
  const before = structuredClone(input);
  const adapted = adaptWorking(input);
  assert.deepEqual(input, before);
  assert.equal(adapted.project.sources[0]?.byteSha256, input.sources[0]?.entry.result.byteSha256);
  assert.equal(adapted.project.sources[0]?.overlays[0]?.text, "User overlay");
  assert.equal(adapted.project.employment[0]?.subprojects[0]?.name, "Local client");
  assert.equal(adapted.project.facts.find((fact) => fact.id === "metric_user_1")?.origin, "user");
  assert.equal(adapted.project.facts.find((fact) => fact.id === "metric_user_1")?.evidence.length, 0);
  assert.equal(adapted.project.facts.find((fact) => fact.id === "lead_user_1")?.kind, "leadership");
  const profile = adapted.project.views.find((block) => block.id === "profile");
  assert.ok(profile);
  assert.ok(profile.state.factIds.includes("metric_user_global"));
  assert.equal(profile.state.factRevisions.metric_user_global, 1);
  assert.match(profile.state.text, /10 systems/);
  assert.match(adapted.project.views.find((block) => block.id === "prose_job_user_1")?.state.text ?? "", /team: at most 20 requests per day.*peak/);
  const known = adapted.project.facts.find((fact) => fact.kind === "technology" && fact.value.display === "Python 3.11");
  assert.equal(known?.kind === "technology" ? known.value.canonicalId : null, "python");
  const unknown = adapted.project.facts.find((fact) => fact.kind === "technology" && fact.value.display === "ObscureDB 2.0");
  assert.equal(unknown?.kind === "technology" ? unknown.value.scope : null, "global");
  assert.match(unknown?.kind === "technology" ? unknown.value.canonicalId : "", /^unknown_user_/);
  const state = editorReducer(initialEditorState, { type: "loadImported", ...adapted, working: input });
  assert.equal(state.working?.sources[0]?.originalBytes[0], 42);
  assert.deepEqual(state.working?.sheet, before.sheet);
  assert.deepEqual(state.working?.manual, before.manual);
});

test("explicit text correction suppresses its typed source fact without guessing a replacement type", () => {
  const input = working();
  const original = input.sheet.facts.find((fact) => fact.kind === "technology" && fact.value.display === "Python");
  assert.ok(original);
  input.sheet.facts.push({ id: "fact_user_correction", revision: 1, kind: "text",
    value: { text: "I did not use Python." }, evidence: [], origin: "user", importance: "normal",
    jobId: null, subprojectId: null });
  input.sheet.userCorrections = { [original.id]: "fact_user_correction" };
  assert.ok(validateFactSheet(input.sheet));
  const adapted = adaptWorking(input);
  assert.equal(adapted.project.facts.some((fact) => fact.id === original.id), false);
  assert.equal(adapted.project.facts.find((fact) => fact.id === "fact_user_correction")?.kind, "text");
  assert.equal(adapted.project.facts.some((fact) => fact.kind === "technology" && fact.value.display === "Python"), false);
  assert.ok(input.sheet.facts.some((fact) => fact.id === original.id));
});

test("manual input rejects incomplete jobs and invalid dates without changing accepted working data", () => {
  const input = working();
  const before = structuredClone(input);
  input.manual.employment[0]!.start = "2025";
  input.manual.employment[0]!.end = "2020";
  assert.throws(() => adaptWorking(input), /Конец периода/);
  assert.deepEqual(input.sheet, before.sheet);
  assert.deepEqual(input.sources, before.sources);
});

test("view adapter namespaces overlapping extracted unit IDs across two sources", () => {
  const input = working();
  const second = structuredClone(input.sources[0]!);
  second.entry.result.sourceId = "source_second";
  input.sources.push(second);
  const adapted = adaptWorking(input);
  assert.notEqual(adapted.project.sources[0]?.units[0]?.id, adapted.project.sources[1]?.units[0]?.id);
  assert.equal(input.sources[0]?.entry.result.units[0]?.id, input.sources[1]?.entry.result.units[0]?.id);
  assert.equal(adapted.project.facts.find((fact) => fact.origin === "source")?.evidence[0]?.unitId,
    adapted.project.sources[0]?.units[0]?.id);
});

test("imported source edit creates a durable text correction and preserves accepted editor work", () => {
  const input = working();
  const evidence = input.sheet.facts[0]?.evidence[0];
  assert.ok(evidence);
  input.sheet.facts.push({ id: "source_profile", revision: 1, kind: "text", value: { text: "Built a service." },
    evidence: [structuredClone(evidence)], origin: "source", importance: "normal", jobId: null, subprojectId: null });
  input.sheet.units[0]?.factIds.push("source_profile");
  assert.ok(validateFactSheet(input.sheet));
  const beforeSheet = structuredClone(input.sheet);
  const beforeBytes = input.sources[0]?.originalBytes.slice();
  let state = editorReducer(initialEditorState, { type: "loadImported", ...adaptWorking(input), working: input });
  state = editorReducer(state, { type: "draft", id: "profile", text: "Reviewed service text." });
  state = editorReducer(state, { type: "apply", id: "profile" });
  assert.ok(state.undo.profile);
  state = editorReducer(state, { type: "draft", id: "education", text: "My accepted education" });
  state = editorReducer(state, { type: "apply", id: "education" });
  state = editorReducer(state, { type: "review", id: "education" });
  state = editorReducer(state, { type: "fact", id: "source_profile", value: "Built a different service." });
  assert.deepEqual(state.working?.sheet.facts.find((fact) => fact.id === "source_profile"),
    beforeSheet.facts.find((fact) => fact.id === "source_profile"));
  assert.deepEqual(state.working?.sources[0]?.originalBytes, beforeBytes);
  const correctionId = state.working?.sheet.userCorrections?.source_profile;
  assert.ok(correctionId);
  const correction = state.working?.sheet.facts.find((fact) => fact.id === correctionId);
  assert.equal(correction?.kind, "text");
  assert.equal(correction?.origin, "user");
  assert.deepEqual(correction?.evidence, []);
  assert.equal(correction?.kind === "text" ? correction.value.text : null, "Built a different service.");
  assert.equal(state.project?.facts.some((fact) => fact.id === "source_profile"), false);
  assert.equal(state.project?.views.find((block) => block.id === "profile")?.status, "stale");
  assert.equal(state.project?.views.find((block) => block.id === "profile")?.state.text, "Reviewed service text.");
  assert.equal(state.undo.profile, undefined);
  assert.ok(state.undo.education);
  assert.equal(state.project?.views.find((block) => block.id === "education")?.state.text, "My accepted education");
  assert.equal(state.project?.review.decisions.some((decision) => decision.targetId === "education"), true);
  assert.ok(validateFactSheet(state.working!.sheet));
  assert.ok(validateContract("project", state.project));
  const roundTrip = adaptWorking(state.working!);
  assert.equal(roundTrip.project.facts.some((fact) => fact.id === "source_profile"), false);
  assert.equal(roundTrip.project.facts.find((fact) => fact.id === correctionId)?.kind, "text");
  state = editorReducer(state, { type: "fact", id: correctionId, value: "Confirmed different service." });
  const corrected = state.working?.sheet.facts.find((fact) => fact.id === correctionId);
  assert.equal(corrected?.kind === "text" ? corrected.value.text : null, "Confirmed different service.");
  assert.equal(state.working?.sheet.facts.find((fact) => fact.id === "source_profile")?.revision, 1);
});

test("imported source metric correction stays user text and manual metric edits persist in working input", () => {
  const input = working();
  const evidence = input.sheet.facts[0]?.evidence[0];
  assert.ok(evidence);
  input.sheet.facts.push({ id: "source_metric", revision: 1, kind: "metric", value: {
    number: 20, upperNumber: null, comparator: "exact", unit: "systems", period: null,
    baseline: null, result: null, scope: null, attribution: "personal", qualifiers: [] },
  evidence: [structuredClone(evidence)], origin: "source", importance: "essential", jobId: null, subprojectId: null });
  input.sheet.units[0]?.factIds.push("source_metric");
  let state = editorReducer(initialEditorState, { type: "loadImported", ...adaptWorking(input), working: input });
  state = editorReducer(state, { type: "fact", id: "source_metric", value: "The count was about twenty." });
  const correctionId = state.working?.sheet.userCorrections?.source_metric;
  assert.ok(correctionId);
  assert.equal(state.working?.sheet.facts.find((fact) => fact.id === "source_metric")?.kind, "metric");
  assert.equal(state.working?.sheet.facts.find((fact) => fact.id === correctionId)?.kind, "text");
  assert.equal(state.project?.facts.find((fact) => fact.id === correctionId)?.kind, "text");
  state = editorReducer(state, { type: "fact", id: "metric_user_global", value: "15" });
  assert.equal(state.working?.manual.metrics.find((metric) => metric.id === "metric_user_global")?.number, 15);
  const metric = state.project?.facts.find((fact) => fact.id === "metric_user_global");
  assert.equal(metric?.kind === "metric" ? metric.value.number : null, 15);
  assert.ok(validateFactSheet(state.working!.sheet));
  assert.ok(validateContract("project", state.project));
});

test("job-scoped source correction keeps the original job evidence and effective job association", () => {
  const input = working();
  const evidence = input.sheet.facts[0]?.evidence[0];
  assert.ok(evidence);
  input.sheet.facts.push({ id: "source_job_text", revision: 1, kind: "text", value: { text: "Built a service." },
    evidence: [structuredClone(evidence)], origin: "source", importance: "essential",
    jobId: "job_source", subprojectId: "sub_source" });
  input.sheet.units[0]?.factIds.push("source_job_text");
  input.sheet.employment = [{ id: "job_source", employer: "Source Works", role: "Engineer",
    sourceId: evidence.sourceId, unitIds: [evidence.unitId], factIds: ["source_job_text"],
    periods: [{ start: { year: 2021, month: null, day: null, precision: "year" },
      end: { year: 2025, month: null, day: null, precision: "year" } }],
    subprojects: [{ id: "sub_source", name: "Service", sourceId: evidence.sourceId,
      unitIds: [evidence.unitId], period: null }] }];
  assert.ok(validateFactSheet(input.sheet));
  let state = editorReducer(initialEditorState, { type: "loadImported", ...adaptWorking(input), working: input });
  state = editorReducer(state, { type: "fact", id: "source_job_text", value: "Worked on a different service." });
  const id = state.working?.sheet.userCorrections?.source_job_text;
  assert.ok(id);
  assert.ok(state.working?.sheet.employment?.[0]?.factIds.includes("source_job_text"));
  assert.ok(state.working?.sheet.employment?.[0]?.factIds.includes(id));
  assert.equal(state.working?.sheet.facts.find((fact) => fact.id === "source_job_text")?.origin, "source");
  assert.equal(state.working?.sheet.facts.find((fact) => fact.id === id)?.jobId, "job_source");
  assert.equal(state.working?.sheet.facts.find((fact) => fact.id === id)?.subprojectId, "sub_source");
  assert.equal(state.project?.employment.find((job) => job.id === "job_source")?.factIds.includes(id), true);
  assert.equal(state.project?.employment.find((job) => job.id === "job_source")?.factIds.includes("source_job_text"), false);
  assert.equal(state.project?.employment.find((job) => job.id === "job_source")?.subprojects[0]?.factIds.includes(id), true);
  assert.equal(state.project?.views.find((block) => block.id === "prose_job_source")?.status, "stale");
  assert.ok(validateFactSheet(state.working!.sheet));
  assert.ok(validateContract("project", state.project));
});

test("undated and partial manual job and subproject periods stay visible as review issues", () => {
  const input = working();
  input.manual.employment[0]!.start = "";
  input.manual.employment[0]!.end = "";
  input.manual.employment[0]!.subprojects[0]!.start = "";
  input.manual.employment[0]!.subprojects[0]!.end = "";
  const absent = adaptWorking(input);
  assert.deepEqual(absent.project.employment[0]?.periods, []);
  assert.equal(absent.project.employment[0]?.subprojects[0]?.period, null);
  assert.ok(absent.issues.some((issue) => issue.includes("Example Works") && issue.includes("не указан период")));
  assert.ok(absent.issues.some((issue) => issue.includes("Local client") && issue.includes("не указан период")));
  input.manual.employment[0]!.start = "2020";
  input.manual.employment[0]!.end = "2025";
  input.manual.employment[0]!.subprojects[0]!.start = "2021-01";
  input.manual.employment[0]!.subprojects[0]!.end = "2023-12";
  const partial = adaptWorking(input);
  assert.ok(partial.issues.some((issue) => issue.includes("Example Works") && issue.includes("частично")));
  assert.ok(partial.issues.some((issue) => issue.includes("Local client") && issue.includes("частично")));
});

test("withheld fact issue identifies its block and stays complete in working draft", () => {
  const input = working();
  input.manual.metrics = input.manual.metrics.filter((metric) => metric.jobId !== null);
  input.sheet.facts.push({ id: "fact_user_safe", revision: 1, kind: "text",
    value: { text: "Built a service." }, evidence: [], origin: "user", importance: "essential",
    jobId: null, subprojectId: null });
  input.sheet.facts.push({ id: "fact_user_private", revision: 1, kind: "text",
    value: { text: "Built a service. Call 555-123-4567." }, evidence: [], origin: "user",
    importance: "essential", jobId: null, subprojectId: null });
  input.draft = { transportVersion: 1, sourceFingerprint: input.sheet.sourceFingerprint,
    baseRevision: input.sheet.revision ?? 1,
    blocks: [{ blockId: "profile", text: "Built a service.", factIds: ["fact_user_safe"] }],
    issues: [{ code: "SOURCE_REVIEW", blockId: "profile", factId: "fact_user_private",
      message: "Fact withheld from drafting because it may contain contact information. Review it manually." }] };
  const complete = structuredClone(input);
  const adapted = adaptDraftedWorking(input);
  assert.deepEqual(input, complete);
  assert.deepEqual(input.draft?.issues, complete.draft?.issues);
  assert.ok(adapted.issues.some((issue) => issue.includes("profile · fact_user_private:") &&
    issue.includes("Fact withheld from drafting")));
  assert.equal(adapted.issues.some((issue) => issue.includes("555-123-4567")), false);
  assert.equal(adapted.project.facts.find((fact) => fact.id === "fact_user_private")?.origin, "user");
  assert.ok(validateFactSheet(input.sheet));
  assert.ok(validateContract("project", adapted.project));
});
