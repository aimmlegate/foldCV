import assert from "node:assert/strict";
import test from "node:test";
import sourceRequest from "../../../contracts/examples/fact_request.json" with { type: "json" };
import sheetFixture from "../../../contracts/examples/fact_sheet.json" with { type: "json" };
import type { ExtractResult } from "../src/contracts/generated/extract_result";
import type { FactSheet } from "../src/contracts/generated/fact_sheet";
import { validateContract, validateExtractResult, validateFactSheet } from "../src/contracts/validate";
import { adaptDraftedWorking, adaptWorking, type ManualInput, type WorkingDraft } from "../src/facts/working";
import { editorReducer, initialEditorState, scopedFactsForBlock } from "../src/editor/state";
import { buildRewriteRequest, currentRewriteDependencyHash, RewriteWorkflow } from "../src/editor/rewriteWorkflow";
import type { RewriteResult } from "../src/contracts/generated/rewrite_result";
import type { RewritePreflightFailure } from "../src/contracts/generated/rewrite_preflight_failure";

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

function imported() {
  const input = working();
  return editorReducer(initialEditorState, { type: "loadImported", loadId: "unit-load", ...adaptWorking(input), working: input });
}

test("real imported job rewrite scopes facts, waits for apply, and undo restores full block state", async () => {
  let state = imported();
  const before = state.project?.views.find((item) => item.id === "prose_job_user_1");
  const other = state.project?.views.find((item) => item.id === "profile");
  assert.ok(before && other);
  const payload = await buildRewriteRequest(state, before, "Make it concise.");
  assert.equal((await buildRewriteRequest(state, before, "")).instruction, "");
  assert.equal(payload.blockKind, "job_prose");
  assert.equal(payload.instruction, "Make it concise.");
  assert.ok(payload.facts.every((fact) => fact.jobId === "job_user_1"));
  assert.equal(payload.facts.some((fact) => fact.id === "metric_user_global"), false);
  assert.equal(JSON.stringify(payload).includes("originalBytes"), false);
  const result: RewriteResult = { transportVersion: 1, baseRevision: payload.baseRevision,
    blockId: payload.blockId, blockRevision: payload.blockRevision, dependencyHash: payload.dependencyHash,
    replacementText: "A clearer local service.", factIds: payload.facts.map((fact) => fact.id), issues: [{
      code: "SOURCE_REVIEW", blockId: payload.blockId, factId: payload.facts[0]!.id, message: "Review source meaning." }] };
  state = editorReducer(state, { type: "rewriteProposed", result });
  assert.equal(state.project?.views.find((item) => item.id === before.id)?.state.text, before.state.text);
  assert.equal(state.rewriteProposal?.result.replacementText, "A clearer local service.");
  state = editorReducer(state, { type: "rewriteApply", id: before.id });
  const applied = state.project?.views.find((item) => item.id === before.id);
  assert.equal(applied?.state.text, "A clearer local service.");
  assert.equal(applied?.state.origin, "generated");
  assert.equal(state.project?.views.find((item) => item.id === other.id), other);
  assert.equal(state.rewriteIssues[before.id]?.length, 1);
  state = editorReducer(state, { type: "undo", id: before.id });
  const restored = state.project?.views.find((item) => item.id === before.id);
  assert.deepEqual(restored?.state, before.state);
  assert.equal(restored?.dependencyHash, before.dependencyHash);
  assert.equal(state.rewriteIssues[before.id]?.length, 0);
  assert.equal(state.working?.sources[0]?.originalBytes[0], 42);
});

test("manual-only job descriptions are stable user facts and remain editable", async () => {
  const input = working();
  input.manual.metrics = [];
  input.manual.leadership = [];
  let state = editorReducer(initialEditorState, { type: "loadImported", loadId: "unit-load", ...adaptWorking(input), working: input });
  const block = state.project!.views.find((item) => item.id === "prose_job_user_1")!;
  const request = await buildRewriteRequest(state, block, "");
  assert.deepEqual(request.requiredFactIds.sort(), ["fact_user_manual_job_job_user_1", "fact_user_manual_sub_sub_user_1"]);
  assert.ok(request.facts.every((fact) => fact.origin === "user" && fact.evidence.length === 0));
  assert.equal(state.working?.sheet.facts.length, input.sheet.facts.length);
  state = editorReducer(state, { type: "fact", id: "fact_user_manual_job_job_user_1", value: "Built a safer tool." });
  assert.equal(state.working?.manual.employment[0]?.description, "Built a safer tool.");
  assert.equal(state.project?.views.find((item) => item.id === block.id)?.status, "stale");
  assert.equal(adaptWorking(state.working!).project.facts.find((fact) => fact.id === "fact_user_manual_job_job_user_1")?.kind, "text");
});

test("profile rewrite recovers recent job facts omitted by an earlier generated block", async () => {
  let state = imported();
  const profile = state.project!.views.find((item) => item.id === "profile")!;
  state = { ...state, project: { ...state.project!, views: state.project!.views.map((item) => item.id === profile.id ?
    { ...item, state: { ...item.state, origin: "generated", factIds: [], factRevisions: {} } } : item) } };
  const request = await buildRewriteRequest(state, state.project!.views.find((item) => item.id === "profile")!, "");
  assert.ok(request.requiredFactIds.includes("fact_user_manual_job_job_user_1"));
  assert.ok(request.requiredFactIds.includes("metric_user_1"));
  assert.ok(request.requiredFactIds.includes("lead_user_1"));
  assert.ok(request.facts.some((fact) => fact.id === "fact_user_manual_sub_sub_user_1"));
  assert.equal(request.facts.some((fact) => fact.jobId === "other_job"), false);
});

test("rewrite rejects the full evidence set instead of truncating it", async () => {
  const state = imported();
  const project = state.project!;
  const source = project.sources[0]!;
  const exampleUnit = source.units[0]!;
  const sourceFact = project.facts.find((fact) => fact.origin === "source")!;
  const units = Array.from({ length: 201 }, (_, index) => ({ ...exampleUnit,
    id: `view_${source.id}_evidence_${index}`, text: `Distinct evidence ${index}` }));
  const evidence = units.map((unit) => ({ sourceId: source.id, sourceRevision: 1,
    unitId: unit.id, unitRevision: 1 }));
  const extended = { ...state, project: { ...project,
    sources: project.sources.map((item) => item.id === source.id ? { ...item, units: [...item.units, ...units] } : item),
    facts: project.facts.map((fact) => fact.id === sourceFact.id ? { ...fact, evidence } : fact),
    views: project.views.map((item) => item.id === "profile" ? { ...item,
      state: { ...item.state, factIds: [...item.state.factIds, sourceFact.id] } } : item) } };
  await assert.rejects(buildRewriteRequest(extended, extended.project.views.find((item) => item.id === "profile")!, ""),
    /Контекст блока превышает предел запроса/);
});

test("late rewrite cannot replace a corrected fact or a manual edit", async () => {
  let state = imported();
  const block = state.project?.views.find((item) => item.id === "prose_job_user_1");
  assert.ok(block);
  const payload = await buildRewriteRequest(state, block, "Shorten.");
  const result: RewriteResult = { transportVersion: 1, baseRevision: payload.baseRevision,
    blockId: block.id, blockRevision: block.revision, dependencyHash: payload.dependencyHash,
    replacementText: "Short draft.", factIds: payload.facts.map((fact) => fact.id), issues: [] };
  state = editorReducer(state, { type: "fact", id: "metric_user_1", value: "22" });
  const afterFact = state.project;
  state = editorReducer(state, { type: "rewriteProposed", result });
  assert.equal(state.rewriteProposal, null);
  assert.equal(state.project, afterFact);
  state = editorReducer(state, { type: "select", id: block.id });
  const currentBlock = state.project!.views.find((item) => item.id === block.id)!;
  const lateHash = currentRewriteDependencyHash(state, currentBlock);
  const replacedProject = { ...state, project: structuredClone(state.project!), loadId: "new-load" };
  const reconcile = { type: "reconcile" as const, id: block.id, projectId: state.project!.projectId, loadId: state.loadId!,
    baseRevision: state.project!.revision, blockRevision: currentBlock.revision,
    dependencyHash: await lateHash };
  const differentSelection = editorReducer(state, { type: "select", id: "profile" });
  assert.equal(editorReducer(differentSelection, reconcile), differentSelection);
  const changedFact = editorReducer(state, { type: "fact", id: "metric_user_1", value: "23" });
  assert.equal(editorReducer(changedFact, reconcile), changedFact);
  assert.equal(replacedProject.project.projectId, reconcile.projectId);
  assert.equal(replacedProject.project.revision, reconcile.baseRevision);
  assert.equal(editorReducer(replacedProject, reconcile), replacedProject);
  state = editorReducer(state, reconcile);
  assert.equal(state.project?.views.find((item) => item.id === block.id)?.status, "ready");
  assert.equal(state.project?.views.find((item) => item.id === block.id)?.dependencyHash, reconcile.dependencyHash);
  assert.equal(state.project?.views.find((item) => item.id === block.id)?.state.text, block.state.text);
  state = editorReducer(state, { type: "undo", id: block.id });
  assert.equal(state.project?.views.find((item) => item.id === block.id)?.status, "stale");
  state = editorReducer(state, { type: "draft", id: block.id, text: "My own wording." });
  state = editorReducer(state, { type: "apply", id: block.id });
  const manual = state.project?.views.find((item) => item.id === block.id);
  assert.equal(manual?.state.locked, true);
  state = editorReducer(state, { type: "rewriteProposed", result: { ...result, baseRevision: state.project!.revision,
    blockRevision: manual!.revision } });
  assert.equal(state.rewriteProposal, null);
});

test("rewrite workflow makes one request and cancellation ignores late result", async () => {
  let state = imported();
  const block = state.project?.views.find((item) => item.id === "prose_job_user_1");
  assert.ok(block);
  let calls = 0;
  let release: () => void = () => { throw new Error("missing release"); };
  const response = new Promise<Response>((resolve) => { release = () => resolve(new Response("late")); });
  const workflow = new RewriteWorkflow(() => undefined, () => { throw new Error("late result applied"); },
    () => { throw new Error("late issue applied"); }, () => {
    calls += 1;
    return response;
  });
  const pending = workflow.run(state, block, "Shorten.", () => true);
  for (let attempt = 0; attempt < 50 && calls === 0; attempt += 1)
    await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(calls, 1);
  workflow.cancel();
  release();
  await pending;
  assert.equal(workflow.view.pending, false);
  assert.equal(workflow.view.completed, 0);
  state = editorReducer(state, { type: "draft", id: block.id, text: "My own text." });
  assert.equal(state.project?.views.find((item) => item.id === block.id)?.state.text, block.state.text);
});

test("typed private preflight links the fact and ignores a late response", async () => {
  let state = imported();
  const block = state.project!.views.find((item) => item.id === "prose_job_user_1")!;
  const payload = await buildRewriteRequest(state, block, "");
  const factId = payload.requiredFactIds[0]!;
  const failure: RewritePreflightFailure = { transportVersion: 1,
    error: { code: "NO_SAFE_CONTENT", retryable: false, stage: "rewrite" },
    baseRevision: payload.baseRevision, blockId: payload.blockId,
    blockRevision: payload.blockRevision, dependencyHash: payload.dependencyHash,
    issues: [{ code: "SOURCE_REVIEW", blockId: payload.blockId, factId,
      message: "Required fact or evidence withheld because it may contain contact information. Review manually." }] };
  const response = () => new Response(JSON.stringify(failure), { status: 422,
    headers: { "Content-Type": "application/json" } });
  const workflow = new RewriteWorkflow(() => undefined, () => { throw new Error("unexpected proposal"); },
    (problem, loadId) => { state = editorReducer(state, { type: "rewritePreflight", result: problem, loadId }); },
    async () => response());
  await workflow.run(state, block, "", () => true);
  assert.match(state.rewriteIssues[block.id]?.[0] ?? "", new RegExp(`${block.id} · ${factId}:`));
  assert.match(workflow.view.error ?? "", /контактные данные/);

  for (const kind of ["cancel", "edit", "replace"] as const) {
    let lateState = imported();
    const lateBlock = lateState.project!.views.find((item) => item.id === block.id)!;
    let calls = 0;
    let release: () => void = () => { throw new Error("missing release"); };
    const pendingResponse = new Promise<Response>((resolve) => { release = () => resolve(response()); });
    let blocked = 0;
    let current = true;
    const late = new RewriteWorkflow(() => undefined, () => { throw new Error("late proposal"); },
      () => { blocked += 1; }, () => { calls += 1; return pendingResponse; });
    const pending = late.run(lateState, lateBlock, "", () => current);
    for (let attempt = 0; attempt < 50 && calls === 0; attempt += 1)
      await new Promise((resolve) => setTimeout(resolve, 5));
    assert.equal(calls, 1);
    if (kind === "cancel") late.cancel();
    if (kind === "edit") { lateState = editorReducer(lateState, { type: "fact", id: factId, value: "Revised fact." }); current = false; }
    if (kind === "replace") { lateState = { ...lateState, project: structuredClone(lateState.project!), loadId: "replacement" }; current = false; }
    release();
    await pending;
    assert.equal(blocked, 0, kind);
  }
});

test("structured corrections preserve source and update deterministic visible fields", () => {
  let state = imported();
  const sourceBefore = structuredClone(state.working?.sheet);
  state = editorReducer(state, { type: "jobField", id: "job_user_1", field: "employer", value: "Safer Works" });
  assert.equal(state.project?.employment.find((job) => job.id === "job_user_1")?.employer, "Safer Works");
  assert.equal(state.working?.manual.employment[0]?.employer, "Safer Works");
  state = editorReducer(state, { type: "subprojectField", jobId: "job_user_1", id: "sub_user_1",
    field: "name", value: "Safer client" });
  assert.equal(state.working?.manual.employment[0]?.subprojects[0]?.name, "Safer client");
  state = editorReducer(state, { type: "jobField", id: "job_user_1", field: "start", value: "2021" });
  assert.equal(state.project?.employment.find((job) => job.id === "job_user_1")?.periods[0]?.start.year, 2021);
  state = editorReducer(state, { type: "languages", value: "English, Serbian" });
  assert.deepEqual(state.presentation?.languages, ["English", "Serbian"]);
  assert.deepEqual(state.working?.manual.languages, ["English", "Serbian"]);
  state = editorReducer(state, { type: "presentationUndo" });
  assert.deepEqual(state.working?.manual.languages, ["English"]);
  state = editorReducer(state, { type: "presentationDraft", field: "name", text: "Alex Corrected" });
  state = editorReducer(state, { type: "presentationApply", field: "name" });
  assert.equal(state.working?.manual.name, "Alex Corrected");
  state = editorReducer(state, { type: "presentationUndo" });
  assert.equal(state.working?.manual.name, "Alex Example");
  state = editorReducer(state, { type: "asOf", value: "2026-10-12" });
  assert.equal(state.project?.asOf?.day, 12);
  assert.deepEqual(state.working?.sheet, sourceBefore);
  assert.equal(state.project?.views.find((item) => item.id === "prose_job_user_1")?.status, "stale");
});

test("source employer correction remains separate and survives the working adapter", () => {
  const input = working();
  const unit = input.sheet.units[0];
  assert.ok(unit);
  input.sheet.employment = [{ id: "job_source", employer: "Unsafe.example", role: "Developer",
    periods: [{ start: { precision: "year", year: 2022, month: null, day: null },
      end: { precision: "year", year: 2025, month: null, day: null } }],
    sourceId: unit.sourceId, unitIds: [unit.unitId], subprojects: [], factIds: [], reviewRequired: true }];
  assert.ok(validateFactSheet(input.sheet));
  let state = editorReducer(initialEditorState, { type: "loadImported", loadId: "unit-load", ...adaptWorking(input), working: input });
  state = editorReducer(state, { type: "jobField", id: "job_source", field: "employer", value: "Safe Works" });
  assert.equal(state.project?.employment.find((job) => job.id === "job_source")?.employer, "Safe Works");
  assert.equal(state.working?.sheet.employment?.[0]?.employer, "Unsafe.example");
  assert.equal(state.working?.structuredCorrections?.["job:job_source:employer"], "Safe Works");
  assert.ok(state.working);
  assert.equal(adaptWorking(state.working).project.employment.find((job) => job.id === "job_source")?.employer, "Safe Works");
});

test("source job and subproject can gain explicit dates without changing the source sheet", () => {
  const input = working();
  const unit = input.sheet.units[0]!;
  input.sheet.employment = [{ id: "job_source", employer: "Example Works", role: "Developer",
    periods: [], sourceId: unit.sourceId, unitIds: [unit.unitId], factIds: [], reviewRequired: true,
    subprojects: [{ id: "sub_source", name: "Local client", period: null,
      sourceId: unit.sourceId, unitIds: [unit.unitId] }] }];
  assert.ok(validateFactSheet(input.sheet));
  let state = editorReducer(initialEditorState, { type: "loadImported", loadId: "unit-load", ...adaptWorking(input), working: input });
  state = editorReducer(state, { type: "jobField", id: "job_source", field: "start", value: "2022" });
  state = editorReducer(state, { type: "subprojectField", jobId: "job_source", id: "sub_source",
    field: "start", value: "2023" });
  assert.equal(state.working?.sheet.employment?.[0]?.periods.length, 0);
  assert.equal(adaptWorking(state.working!).project.employment.find((job) => job.id === "job_source")?.periods[0]?.start.year, 2022);
  assert.equal(adaptWorking(state.working!).project.employment.find((job) => job.id === "job_source")?.subprojects[0]?.period?.start.year, 2023);
});

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
  const state = editorReducer(initialEditorState, { type: "loadImported", loadId: "unit-load", ...adapted, working: input });
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
  let state = editorReducer(initialEditorState, { type: "loadImported", loadId: "unit-load", ...adaptWorking(input), working: input });
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
  let state = editorReducer(initialEditorState, { type: "loadImported", loadId: "unit-load", ...adaptWorking(input), working: input });
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
  let state = editorReducer(initialEditorState, { type: "loadImported", loadId: "unit-load", ...adaptWorking(input), working: input });
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

test("newly eligible global source correction stales only the profile and drops its proposal", async () => {
  let state = imported();
  const source = state.project!.facts.find((fact) => fact.origin === "source" && fact.kind === "technology" &&
    fact.value.canonicalId === "python")!;
  const profile = state.project!.views.find((block) => block.id === "profile")!;
  const job = state.project!.views.find((block) => block.id === "prose_job_user_1")!;
  assert.equal(scopedFactsForBlock(state, profile).some((fact) => fact.id === source.id), false);
  state = editorReducer(state, { type: "review", id: profile.id });
  state = editorReducer(state, { type: "review", id: job.id });
  const payload = await buildRewriteRequest(state, profile, "");
  state = editorReducer(state, { type: "rewriteProposed", result: {
    transportVersion: 1, baseRevision: payload.baseRevision, blockId: profile.id,
    blockRevision: profile.revision, dependencyHash: payload.dependencyHash,
    replacementText: "Proposed profile.", factIds: payload.facts.map((fact) => fact.id), issues: [] } });
  assert.ok(state.rewriteProposal);
  const unrelated = state.project!.views.find((block) => block.id === job.id)!;
  state = editorReducer(state, { type: "fact", id: source.id, value: "docker" });
  const correctionId = state.working?.sheet.userCorrections?.[source.id];
  assert.ok(correctionId);
  assert.equal(state.project?.views.find((block) => block.id === profile.id)?.status, "stale");
  assert.equal(state.project?.review.decisions.some((item) => item.targetKind === "block" && item.targetId === profile.id), false);
  assert.equal(state.rewriteProposal, null);
  assert.equal(state.project?.views.find((block) => block.id === job.id), unrelated);
  assert.equal(state.project?.review.decisions.some((item) => item.targetKind === "block" && item.targetId === job.id), true);
  assert.ok(scopedFactsForBlock(state, state.project!.views.find((block) => block.id === profile.id)!)
    .some((fact) => fact.id === correctionId && fact.origin === "user"));
  assert.equal(state.working?.sheet.facts.find((fact) => fact.id === source.id)?.origin, "source");
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
