import assert from "node:assert/strict";
import test from "node:test";
import sourceRequest from "../../../contracts/examples/fact_request.json" with { type: "json" };
import sheetFixture from "../../../contracts/examples/fact_sheet.json" with { type: "json" };
import type { ExtractResult } from "../src/contracts/generated/extract_result";
import type { FactSheet } from "../src/contracts/generated/fact_sheet";
import type { Project } from "../src/contracts/generated/project";
import { coverageReview, verifyWorkingSources } from "../src/editor/coverage";
import { editorReducer, initialEditorState } from "../src/editor/state";
import type { EditorState } from "../src/editor/state";
import { adaptWorking } from "../src/facts/working";
import type { WorkingDraft } from "../src/facts/working";

function fixture(): EditorState {
  const result = structuredClone(sourceRequest.sources[0]!.result) as ExtractResult;
  const sheet = structuredClone(sheetFixture) as FactSheet;
  const working: WorkingDraft = { transportVersion: 1,
    sources: [{ entry: { result, overlays: {} }, originalBytes: new Uint8Array(result.byteLength) }],
    sheet, priorSheet: null, sourceReviewStale: false, draft: null,
    manual: { name: "Alex Example", title: "Engineer", asOf: "2026-10-11", education: "",
      language: "en", languages: [], skills: ["ObscureDB"], employment: [
        { id: "recent", employer: "Recent Works", role: "Engineer", start: "2022", end: "2025",
          description: "Built a service for the team.", subprojects: [] },
        { id: "old", employer: "Old Works", role: "Developer", start: "2001", end: "2005",
          description: "Maintained a legacy system.", subprojects: [] }],
      metrics: [{ id: "metric", jobId: "recent", number: 20, upperNumber: null,
        comparator: "at_most", unit: "requests", period: "day", baseline: null,
        result: null, scope: "service", attribution: "team", qualifiers: ["peak"] }],
      leadership: [{ id: "lead", jobId: "recent", action: "Built the team",
        attribution: "team", teamSize: 5, teamUnit: "engineers", teamBaseline: "zero" }] } };
  return editorReducer(initialEditorState, { type: "loadImported", loadId: "coverage-load", ...adaptWorking(working), working });
}

function report(state: EditorState) {
  assert.ok(state.project);
  return coverageReview({ project: state.project, working: state.working,
    presentation: state.presentation, rewriteIssues: state.rewriteIssueDetails,
    sourceIntegrity: state.sourceIntegrity });
}

function setProject(state: EditorState, project: Project): EditorState {
  return { ...state, project };
}

function rewrite(state: EditorState, blockId: string, text: string): EditorState {
  const block = state.project?.views.find((item) => item.id === blockId);
  assert.ok(block && state.project);
  const proposed = editorReducer(state, { type: "rewriteProposed", result: {
    transportVersion: 1, baseRevision: state.project.revision, blockId,
    blockRevision: block.revision, dependencyHash: "0".repeat(64),
    replacementText: text, factIds: [], issues: [] } });
  assert.ok(proposed.rewriteProposal);
  return editorReducer(proposed, { type: "rewriteApply", id: blockId });
}

test("removed recent job blocks while a hidden old prose block remains condensed", () => {
  let state = fixture();
  state = editorReducer(state, { type: "visible", id: "prose_old" });
  assert.equal(report(state).blockers.some((item) => item.jobId === "old"), false);
  assert.equal(report(state).facts.find((item) => item.id === "fact_user_manual_job_old")?.disposition, "unresolved");
  state = editorReducer(state, { type: "visible", id: "prose_recent" });
  const missing = report(state).blockers.find((item) => item.code === "MISSING_JOB" && item.jobId === "recent");
  assert.ok(missing);
  state = editorReducer(state, { type: "coverageDecision", targetKind: "job", targetId: "recent",
    disposition: "excluded", reason: "", dependency: missing.dependency });
  assert.ok(report(state).blockers.some((item) => item.jobId === "recent"));
  state = editorReducer(state, { type: "coverageDecision", targetKind: "job", targetId: "recent",
    disposition: "excluded", reason: "Role outside this resume", dependency: missing.dependency });
  assert.equal(report(state).blockers.some((item) => item.jobId === "recent"), false);
  state = editorReducer(state, { type: "visible", id: "early_career" });
  assert.ok(report(state).blockers.some((item) => item.jobId === "old"));
});

test("removing a retained job record from the view remains a missing-job blocker", () => {
  const state = fixture();
  const project = state.project!;
  const removed = setProject(state, { ...project,
    employment: project.employment.filter((job) => job.id !== "recent"),
    facts: project.facts.filter((fact) => fact.jobId !== "recent"),
    views: project.views.filter((block) => block.id !== "prose_recent") });
  assert.ok(report(removed).blockers.some((item) => item.code === "MISSING_JOB" && item.jobId === "recent"));
});

test("essential omission blocks until explicit reason; normal omission remains a warning", () => {
  let state = fixture();
  const id = "fact_user_manual_job_recent";
  const facts = state.project!.facts.map((fact) => fact.id === id ? { ...fact, importance: "essential" as const } : fact);
  const views = state.project!.views.map((block) => block.id === "prose_recent" ? { ...block,
    state: { ...block.state, factIds: block.state.factIds.filter((factId) => factId !== id),
      factRevisions: Object.fromEntries(Object.entries(block.state.factRevisions).filter(([factId]) => factId !== id)) } } : block);
  state = setProject(state, { ...state.project!, facts, views });
  const missing = report(state).blockers.find((item) => item.code === "MISSING_ESSENTIAL" && item.factId === id);
  assert.ok(missing);
  const target = report(state).facts.find((item) => item.id === id)!;
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: id,
    disposition: "excluded", reason: "Not relevant to this role", dependency: target.dependency });
  assert.equal(report(state).blockers.some((item) => item.factId === id), false);
  assert.ok(report(state).warnings.some((item) => item.code === "UNRESOLVED_UNIT"));
});

test("qualifier, credit and leadership warnings are typed and revision bound", () => {
  let state = fixture();
  const warning = report(state).warnings.find((item) => item.code === "METRIC_MEANING" && item.factId === "metric");
  assert.ok(warning);
  assert.ok(report(state).warnings.some((item) => item.code === "ATTRIBUTION" && item.factId === "metric"));
  assert.ok(report(state).warnings.some((item) => item.code === "LEADERSHIP_SCOPE" && item.factId === "lead"));
  state = editorReducer(state, { type: "coverageAcknowledge", issueId: warning.id, dependency: warning.dependency });
  assert.equal(report(state).warnings.find((item) => item.id === warning.id)?.acknowledged, true);
  state = editorReducer(state, { type: "draft", id: "prose_recent", text: "Built a changed service." });
  state = editorReducer(state, { type: "apply", id: "prose_recent" });
  assert.equal(report(state).warnings.find((item) => item.id === warning.id)?.acknowledged, false);
});

test("unrelated decisions survive edits and undo restores relevant review checkpoint", () => {
  let state = fixture();
  const unit = report(state).units.find((item) => item.unitId === "unit_2")!;
  state = editorReducer(state, { type: "coverageDecision", targetKind: "unit", targetId: unit.id,
    disposition: "excluded", reason: "Unclear date", dependency: unit.dependency });
  const warning = report(state).warnings.find((item) => item.code === "LEADERSHIP_SCOPE")!;
  state = editorReducer(state, { type: "coverageAcknowledge", issueId: warning.id, dependency: warning.dependency });
  state = editorReducer(state, { type: "draft", id: "prose_recent", text: "Updated prose." });
  state = editorReducer(state, { type: "apply", id: "prose_recent" });
  assert.equal(report(state).warnings.find((item) => item.id === warning.id)?.acknowledged, false);
  assert.equal(report(state).units.find((item) => item.id === unit.id)?.disposition, "excluded");
  state = editorReducer(state, { type: "undo", id: "prose_recent" });
  assert.equal(report(state).warnings.find((item) => item.id === warning.id)?.acknowledged, true);
  assert.equal(report(state).units.find((item) => item.id === unit.id)?.disposition, "excluded");
});

test("source and fact coverage stay separate across duplicates and corrections", () => {
  let state = fixture();
  assert.ok(report(state).units.some((item) => item.disposition === "unresolved"));
  const source = state.project!.facts.find((fact) => fact.origin === "source" && fact.kind === "technology")!;
  state = editorReducer(state, { type: "fact", id: source.id, value: "docker" });
  assert.ok(state.working?.sheet.facts.some((fact) => fact.id === source.id));
  const correction = state.working?.sheet.userCorrections?.[source.id];
  assert.ok(correction && state.project?.facts.find((fact) => fact.id === correction)?.origin === "user");
  assert.ok(report(state).units.find((item) => `view_${item.sourceId}_${item.unitId}` === source.evidence[0]?.unitId));
  assert.equal(state.project?.operations.length, 0);
});

test("pending proposal cannot certify an omitted fact or start inference", () => {
  const state = fixture();
  const missing = { id: "user_essential", revision: 1, kind: "text" as const,
    value: { text: "A source assertion" }, evidence: [], origin: "user" as const,
    importance: "essential" as const, jobId: null, subprojectId: null };
  const proposed = setProject(state, { ...state.project!, facts: [...state.project!.facts, missing],
    views: state.project!.views.map((block) =>
    block.kind === "profile" ? { ...block, status: "proposed", state: { ...block.state,
      factIds: [...block.state.factIds, missing.id],
      factRevisions: { ...block.state.factRevisions, [missing.id]: missing.revision } } } : block) });
  assert.equal(report(proposed).facts.find((item) => item.id === missing.id)?.disposition, "unresolved");
  assert.ok(report(proposed).blockers.some((item) => item.factId === missing.id));
  assert.equal(proposed.project?.operations.length, 0);
});

test("old-job detail needs its own decision even when the employment line renders", () => {
  const state = fixture();
  const id = "fact_user_manual_job_old";
  const facts = state.project!.facts.map((fact) => fact.id === id ?
    { ...fact, importance: "essential" as const } : fact);
  const current = report(setProject(state, { ...state.project!, facts }));
  assert.equal(current.blockers.some((item) => item.jobId === "old"), false);
  assert.ok(current.blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === id));
});

test("duplicate unit stays distinct from unresolved and a corrected source fact", () => {
  const state = fixture();
  const sheet = structuredClone(state.working!.sheet);
  const second = sheet.units[1]!;
  const first = sheet.units[0]!;
  sheet.units[1] = { ...second, disposition: "duplicate",
    duplicateOf: `${first.sourceId}:${first.unitId}` };
  const changed = { ...state, working: { ...state.working!, sheet } };
  assert.equal(report(changed).units.find((item) => item.unitId === second.unitId)?.disposition, "duplicate");
  assert.equal(report(changed).warnings.some((item) => item.code === "UNRESOLVED_UNIT" &&
    item.unitId === second.unitId), false);
});

test("number tokens reject 20 embedded in 200", () => {
  const state = fixture();
  const facts = state.project!.facts.map((fact) => fact.id === "metric" && fact.kind === "metric" ?
    { ...fact, value: { ...fact.value, comparator: "exact" as const,
      attribution: "personal" as const, period: null, scope: null, qualifiers: [] } } : fact);
  const views = state.project!.views.map((block) => block.id === "prose_recent" ? { ...block,
    state: { ...block.state, text: "Processed 200 requests." } } : block);
  const changed = setProject(state, { ...state.project!, facts, views });
  assert.ok(report(changed).warnings.some((item) => item.code === "METRIC_MEANING" && item.factId === "metric"));
  const exact = setProject(changed, { ...changed.project!, views: changed.project!.views.map((block) =>
    block.id === "prose_recent" ? { ...block, state: { ...block.state, text: "Processed 20 requests." } } : block) });
  assert.equal(report(exact).warnings.some((item) => item.code === "METRIC_MEANING" && item.factId === "metric"), false);
});

test("global and obscure technology is shown only while skills output is visible", () => {
  let state = fixture();
  const obscure = report(state).facts.find((item) => item.id === "fact_user_skill_0")!;
  assert.equal(obscure.disposition, "shown");
  state = editorReducer(state, { type: "visible", id: "skills" });
  assert.equal(report(state).facts.find((item) => item.id === obscure.id)?.disposition, "unresolved");
});

test("one shown fact cannot settle an unresolved or partly covered source unit", () => {
  const state = fixture();
  const sheet = structuredClone(state.working!.sheet);
  const first = sheet.units[0]!;
  assert.equal(first.disposition, "facts");
  sheet.units[0] = { ...first, disposition: "unresolved" };
  const unresolved = { ...state, working: { ...state.working!, sheet } };
  assert.equal(report(unresolved).units.find((item) => item.unitId === first.unitId)?.disposition, "unresolved");

  const sourceFact = sheet.facts.find((fact) => fact.origin === "source")!;
  const extra = { id: "extra_detail", revision: 1, kind: "text" as const,
    value: { text: "Unrepresented detail" }, evidence: sourceFact.evidence,
    origin: "source" as const, importance: "essential" as const,
    jobId: null, subprojectId: null };
  sheet.facts.push(extra);
  sheet.units[0] = { ...first, factIds: [...first.factIds, extra.id] };
  const sources = state.project!.sources.map((source) => ({ ...source, units: source.units.map((unit) =>
    unit.id === `view_${first.sourceId}_${first.unitId}` ? { ...unit,
      representedFactIds: [...unit.representedFactIds, extra.id] } : unit) }));
  const projectFact = { ...extra, evidence: extra.evidence.map((item) => ({ ...item,
    unitId: `view_${item.sourceId}_${item.unitId}` })) };
  const partial = { ...state, working: { ...state.working!, sheet },
    project: { ...state.project!, sources, facts: [...state.project!.facts, projectFact] } };
  assert.equal(report(partial).units.find((item) => item.unitId === first.unitId)?.disposition, "unresolved");
  assert.ok(report(partial).blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === extra.id));
});

test("retained essential sheet fact stays reviewable after removal from project", () => {
  const state = fixture();
  const sheet = structuredClone(state.working!.sheet);
  const original = sheet.facts[0]!;
  sheet.facts[0] = { ...original, importance: "essential" };
  const project = state.project!;
  const removed = { ...state, working: { ...state.working!, sheet }, project: { ...project,
    facts: project.facts.filter((fact) => fact.id !== original.id),
    sources: project.sources.map((source) => ({ ...source, units: source.units.map((unit) => ({ ...unit,
      representedFactIds: unit.representedFactIds.filter((id) => id !== original.id) })) })) } };
  const current = report(removed);
  assert.equal(current.blockers.some((item) => item.code === "CORRUPT_DATA"), false);
  assert.equal(current.facts.find((item) => item.id === original.id)?.disposition, "unresolved");
  assert.ok(current.blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === original.id));
  const target = current.facts.find((item) => item.id === original.id)!;
  const excluded = editorReducer(removed, { type: "coverageDecision", targetKind: "fact", targetId: original.id,
    disposition: "excluded", reason: "Out of scope", dependency: target.dependency });
  assert.equal(report(excluded).blockers.some((item) => item.factId === original.id), false);
});

test("valid correction replaces an original retained fact once", () => {
  const state = fixture();
  const sheet = structuredClone(state.working!.sheet);
  const original = sheet.facts[0]!;
  sheet.facts[0] = { ...original, importance: "essential" };
  const replacement = { id: "corrected_source_fact", revision: 1, kind: "text" as const,
    value: { text: "A reviewed replacement" }, evidence: [], origin: "user" as const,
    importance: "normal" as const, jobId: null, subprojectId: null };
  sheet.facts.push(replacement);
  sheet.userCorrections = { ...sheet.userCorrections, [original.id]: replacement.id };
  const working = { ...state.working!, sheet };
  const { project, presentation } = adaptWorking(working);
  const corrected = { ...state, project, presentation, working };
  assert.equal(report(corrected).blockers.some((item) => item.code === "CORRUPT_DATA"), false);
  assert.equal(report(corrected).facts.some((item) => item.id === original.id), false);
  assert.equal(report(corrected).facts.filter((item) => item.id === replacement.id).length, 1);
  assert.equal(report(corrected).blockers.some((item) => item.code === "MISSING_ESSENTIAL" &&
    item.factId === original.id), false);
});

test("skills changes expire dependent decisions while unrelated prose decisions remain", () => {
  let state = fixture();
  state = editorReducer(state, { type: "visible", id: "skills" });
  const technology = report(state).facts.find((item) => item.id === "fact_user_skill_0")!;
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: technology.id,
    disposition: "excluded", reason: "Role focus", dependency: technology.dependency });
  const prose = report(state).facts.find((item) => item.id === "fact_user_manual_job_old")!;
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: prose.id,
    disposition: "excluded", reason: "Older role", dependency: prose.dependency });
  state = editorReducer(state, { type: "visible", id: "skills" });
  assert.equal(report(state).facts.find((item) => item.id === technology.id)?.disposition, "shown");
  assert.equal(report(state).facts.find((item) => item.id === prose.id)?.disposition, "excluded");
  state = editorReducer(state, { type: "visible", id: "skills" });
  assert.equal(report(state).facts.find((item) => item.id === technology.id)?.disposition, "unresolved");
  assert.equal(report(state).facts.find((item) => item.id === prose.id)?.disposition, "excluded");
});

test("typed preflight issue keeps its fact and block identity without string parsing", () => {
  let state = fixture();
  const block = state.project!.views.find((item) => item.id === "prose_recent")!;
  const result = { baseRevision: state.project!.revision, blockId: block.id,
    blockRevision: block.revision, dependencyHash: "0".repeat(64), transportVersion: 1 as const,
    error: { code: "NO_SAFE_CONTENT" as const, retryable: false as const, stage: "rewrite" as const },
    issues: [{ code: "SOURCE_REVIEW" as const, blockId: block.id,
      factId: "metric", message: "Display text is deliberately irrelevant to identity." }] };
  state = editorReducer(state, { type: "rewritePreflight", loadId: "wrong-open", result });
  assert.equal(report(state).warnings.some((item) => item.code === "REWRITE_SOURCE_REVIEW"), false);
  state = editorReducer(state, { type: "rewritePreflight", loadId: state.loadId!, result });
  const warning = report(state).warnings.find((item) => item.code === "REWRITE_SOURCE_REVIEW");
  assert.equal(warning?.factId, "metric");
  assert.equal(warning.blockId, block.id);
  assert.equal(state.project?.operations.length, 0);
});

test("linked IDs cannot settle replaced prose; reviewed paraphrase expires with its block", () => {
  let state = fixture();
  const essentialId = "fact_user_manual_job_recent";
  const normal = { id: "normal_detail", revision: 1, kind: "text" as const,
    value: { text: "Supported a payment queue" }, evidence: [], origin: "user" as const,
    importance: "normal" as const, jobId: "recent", subprojectId: null };
  const project = state.project!;
  state = setProject(state, { ...project,
    facts: [...project.facts.map((fact) => fact.id === essentialId ?
      { ...fact, importance: "essential" as const } : fact), normal],
    employment: project.employment.map((job) => job.id === "recent" ?
      { ...job, factIds: [...job.factIds, normal.id] } : job),
    views: project.views.map((block) => block.id === "prose_recent" ? { ...block,
      state: { ...block.state, text: `${block.state.text}\n${normal.value.text}`,
        factIds: [...block.state.factIds, normal.id],
        factRevisions: { ...block.state.factRevisions, [normal.id]: normal.revision } } } : block) });
  assert.equal(report(state).facts.find((item) => item.id === essentialId)?.disposition, "shown");
  assert.ok(report(state).warnings.some((item) => item.code === "TEXT_MEANING" && item.factId === essentialId));
  state = editorReducer(state, { type: "draft", id: "prose_recent", text: "Built an unrelated game." });
  state = editorReducer(state, { type: "apply", id: "prose_recent" });
  assert.equal(report(state).facts.find((item) => item.id === essentialId)?.disposition, "unresolved");
  assert.ok(report(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === essentialId));
  assert.ok(report(state).warnings.some((item) => item.code === "OMITTED_FACT" && item.factId === normal.id));
  const target = report(state).facts.find((item) => item.id === essentialId)!;
  assert.equal(target.confirmable, true);
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: essentialId,
    disposition: "shown", reason: "", dependency: target.dependency });
  assert.ok(report(state).blockers.some((item) => item.factId === essentialId));
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: essentialId,
    disposition: "shown", reason: "Reviewed equivalent wording against source", dependency: target.dependency });
  assert.equal(report(state).facts.find((item) => item.id === essentialId)?.disposition, "shown");
  assert.equal(report(state).blockers.some((item) => item.factId === essentialId), false);
  assert.ok(report(state).warnings.some((item) => item.code === "TEXT_MEANING" && item.factId === essentialId));
  state = editorReducer(state, { type: "draft", id: "prose_recent", text: "A later unrelated rewrite." });
  state = editorReducer(state, { type: "apply", id: "prose_recent" });
  assert.ok(report(state).blockers.some((item) => item.factId === essentialId));
  state = editorReducer(state, { type: "undo", id: "prose_recent" });
  assert.equal(report(state).facts.find((item) => item.id === essentialId)?.disposition, "shown");
  assert.equal(report(state).blockers.some((item) => item.factId === essentialId), false);
});

test("profile rewrite can represent a recent job fact; profile review expires and undo restores", () => {
  let state = fixture();
  const id = "fact_user_manual_job_recent";
  const value = state.project!.facts.find((fact) => fact.id === id)!;
  if (value.kind !== "text") throw new Error("Expected text fact");
  state = setProject(state, { ...state.project!, facts: state.project!.facts.map((fact) =>
    fact.id === id ? { ...fact, importance: "essential" as const } : fact) });
  state = rewrite(state, "prose_recent", "A different contribution.");
  assert.ok(report(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === id));
  state = rewrite(state, "profile", value.value.text);
  let target = report(state).facts.find((item) => item.id === id)!;
  assert.equal(target.disposition, "shown");
  assert.equal(target.blockId, "profile");
  assert.equal(report(state).blockers.some((item) => item.factId === id), false);
  let warning = report(state).warnings.find((item) => item.code === "TEXT_MEANING" && item.factId === id)!;
  assert.equal(warning.blockId, "profile");
  state = editorReducer(state, { type: "coverageAcknowledge", issueId: warning.id, dependency: warning.dependency });
  assert.equal(report(state).warnings.find((item) => item.id === warning.id)?.acknowledged, true);
  state = rewrite(state, "profile", "An equivalent backend contribution.");
  target = report(state).facts.find((item) => item.id === id)!;
  assert.equal(target.disposition, "unresolved");
  assert.equal(target.blockId, "profile");
  assert.equal(target.confirmable, true);
  assert.ok(report(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === id));
  assert.equal(state.working?.coverage?.acknowledgments.some((item) => item.issueId === warning.id), false);
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: id,
    disposition: "shown", reason: "Reviewed the equivalent wording against the source", dependency: target.dependency });
  warning = report(state).warnings.find((item) => item.code === "TEXT_MEANING" && item.factId === id)!;
  assert.equal(warning.blockId, "profile");
  state = editorReducer(state, { type: "coverageAcknowledge", issueId: warning.id, dependency: warning.dependency });
  const savedReason = report(state).facts.find((item) => item.id === id)?.reason;
  state = rewrite(state, "profile", "A separate unrelated claim.");
  assert.ok(report(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === id));
  assert.equal(state.working?.coverage?.decisions.some((item) => item.targetId === id), false);
  state = editorReducer(state, { type: "undo", id: "profile" });
  target = report(state).facts.find((item) => item.id === id)!;
  assert.equal(target.disposition, "shown");
  assert.equal(target.reason, savedReason);
  assert.equal(target.blockId, "profile");
  assert.equal(report(state).warnings.find((item) => item.id === warning.id)?.acknowledged, true);
  assert.equal(report(state).blockers.some((item) => item.factId === id), false);
  state = rewrite(state, "prose_old", "Old prose changed outside this fact.");
  assert.equal(report(state).facts.find((item) => item.id === id)?.reason, savedReason);
  assert.equal(report(state).warnings.find((item) => item.id === warning.id)?.acknowledged, true);
  state = editorReducer(state, { type: "visible", id: "profile" });
  assert.ok(report(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === id));
  assert.equal(state.working?.coverage?.decisions.some((item) => item.targetId === id), false);
  state = editorReducer(state, { type: "undo", id: "profile" });
  assert.equal(report(state).facts.find((item) => item.id === id)?.reason, savedReason);
  assert.equal(report(state).warnings.find((item) => item.id === warning.id)?.acknowledged, true);
});

test("profile undo restores only review whose other representing blocks are unchanged", () => {
  let state = fixture();
  const id = "fact_user_manual_job_recent";
  const unrelated = report(state).facts.find((item) => item.id === "fact_user_manual_job_old")!;
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: unrelated.id,
    disposition: "excluded", reason: "Keep old detail in the project", dependency: unrelated.dependency });
  state = rewrite(state, "prose_recent", "A different contribution.");
  state = rewrite(state, "profile", "Equivalent backend contribution.");
  let target = report(state).facts.find((item) => item.id === id)!;
  assert.equal(target.blockId, "profile");
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: id,
    disposition: "shown", reason: "Checked equivalent wording", dependency: target.dependency });
  let warning = report(state).warnings.find((item) => item.code === "TEXT_MEANING" && item.factId === id)!;
  state = editorReducer(state, { type: "coverageAcknowledge", issueId: warning.id, dependency: warning.dependency });
  state = rewrite(state, "profile", "Another claim.");
  state = rewrite(state, "prose_old", "Unrelated old-job detail changed.");
  state = editorReducer(state, { type: "undo", id: "profile" });
  assert.equal(report(state).facts.find((item) => item.id === id)?.disposition, "shown");
  assert.equal(report(state).warnings.find((item) => item.id === warning.id)?.acknowledged, true);
  assert.equal(report(state).facts.find((item) => item.id === unrelated.id)?.reason, "Keep old detail in the project");
  state = rewrite(state, "profile", "Another unrelated claim.");
  state = rewrite(state, "prose_recent", "The owning prose changed too.");
  state = editorReducer(state, { type: "undo", id: "profile" });
  target = report(state).facts.find((item) => item.id === id)!;
  assert.equal(target.disposition, "unresolved");
  assert.equal(state.working?.coverage?.decisions.some((item) => item.targetId === id), false);
  assert.equal(state.working?.coverage?.acknowledgments.some((item) => item.issueId === warning.id), false);
  assert.equal(report(state).facts.find((item) => item.id === unrelated.id)?.reason, "Keep old detail in the project");
});

test("hidden, stale, and unaccepted profile text cannot represent a job fact", () => {
  let state = fixture();
  const id = "fact_user_manual_job_recent";
  const value = state.project!.facts.find((fact) => fact.id === id)!;
  if (value.kind !== "text") throw new Error("Expected text fact");
  state = setProject(state, { ...state.project!, facts: state.project!.facts.map((fact) =>
    fact.id === id ? { ...fact, importance: "essential" as const } : fact) });
  state = rewrite(state, "prose_recent", "A different contribution.");
  state = rewrite(state, "profile", value.value.text);
  const profile = state.project!.views.find((item) => item.id === "profile")!;
  const checks = [
    { ...profile, visible: false },
    { ...profile, status: "stale" as const },
    { ...profile, status: "proposed" as const },
  ];
  for (const candidate of checks) {
    const changed = setProject(state, { ...state.project!, views: state.project!.views.map((block) =>
      block.id === "profile" ? candidate : block) });
    assert.equal(report(changed).facts.find((item) => item.id === id)?.disposition, "unresolved");
    assert.ok(report(changed).blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === id));
    assert.equal(report(changed).facts.find((item) => item.id === id)?.blockId, "prose_recent");
  }
  state = editorReducer(state, { type: "visible", id: "profile" });
  assert.equal(report(state).facts.find((item) => item.id === id)?.blockId, "prose_recent");
  assert.ok(report(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === id));
  state = editorReducer(state, { type: "undo", id: "profile" });
  assert.equal(report(state).facts.find((item) => item.id === id)?.disposition, "shown");
});

test("visible profile can represent old-job detail while hidden old prose cannot", () => {
  let state = fixture();
  const id = "fact_user_manual_job_old";
  const value = state.project!.facts.find((fact) => fact.id === id)!;
  if (value.kind !== "text") throw new Error("Expected text fact");
  state = setProject(state, { ...state.project!, views: state.project!.views.map((block) =>
    block.id === "profile" ? { ...block, state: { ...block.state,
      factIds: [...block.state.factIds, id],
      factRevisions: { ...block.state.factRevisions, [id]: value.revision } } } : block) });
  state = rewrite(state, "profile", value.value.text);
  assert.equal(report(state).facts.find((item) => item.id === id)?.disposition, "shown");
  assert.equal(report(state).facts.find((item) => item.id === id)?.blockId, "profile");
  state = editorReducer(state, { type: "visible", id: "prose_old" });
  assert.equal(report(state).facts.find((item) => item.id === id)?.disposition, "shown");
  state = editorReducer(state, { type: "visible", id: "profile" });
  assert.equal(report(state).facts.find((item) => item.id === id)?.disposition, "unresolved");
});

test("replaced profile prose leaves its linked source unit unresolved", () => {
  const state = fixture();
  const sheet = structuredClone(state.working!.sheet);
  const first = sheet.units[0]!;
  const sourceFact = sheet.facts[0]!;
  const text = { id: "source_profile_detail", revision: 1, kind: "text" as const,
    value: { text: "Built a payment service" }, evidence: sourceFact.evidence,
    origin: "source" as const, importance: "essential" as const,
    jobId: null, subprojectId: null };
  sheet.facts.push(text);
  sheet.units[0] = { ...first, factIds: [...first.factIds, text.id] };
  const project = state.project!;
  const profile = project.views.find((item) => item.kind === "profile")!;
  const added = { ...state, working: { ...state.working!, sheet }, project: { ...project,
    facts: [...project.facts, { ...text, evidence: text.evidence.map((item) => ({ ...item,
      unitId: `view_${item.sourceId}_${item.unitId}` })) }],
    sources: project.sources.map((source) => ({ ...source, units: source.units.map((unit) =>
      unit.id === `view_${first.sourceId}_${first.unitId}` ? { ...unit,
        representedFactIds: [...unit.representedFactIds, text.id] } : unit) })),
    views: project.views.map((block) => block.id === profile.id ? { ...block,
      state: { ...block.state, text: `${block.state.text}\n${text.value.text}`,
        factIds: [...block.state.factIds, text.id],
        factRevisions: { ...block.state.factRevisions, [text.id]: text.revision } } } : block) } };
  assert.equal(report(added).facts.find((item) => item.id === text.id)?.disposition, "shown");
  const changed = editorReducer(editorReducer(added, { type: "draft", id: profile.id,
    text: "Built an unrelated game." }), { type: "apply", id: profile.id });
  assert.equal(report(changed).facts.find((item) => item.id === text.id)?.disposition, "unresolved");
  assert.equal(report(changed).units.find((item) => item.unitId === first.unitId)?.disposition, "unresolved");
  assert.ok(report(changed).blockers.some((item) => item.code === "MISSING_ESSENTIAL" && item.factId === text.id));
});

test("source-origin unit exclusion and fact acknowledgment return on profile undo", () => {
  const state = fixture();
  const sheet = structuredClone(state.working!.sheet);
  const first = sheet.units[0]!;
  const sourceFact = sheet.facts[0]!;
  const text = { id: "source_review_detail", revision: 1, kind: "text" as const,
    value: { text: "Built a payment service" }, evidence: sourceFact.evidence,
    origin: "source" as const, importance: "normal" as const,
    jobId: null, subprojectId: null };
  sheet.facts.push(text);
  sheet.units[0] = { ...first, factIds: [...first.factIds, text.id] };
  const project = state.project!;
  const profile = project.views.find((item) => item.kind === "profile")!;
  let current: EditorState = { ...state, working: { ...state.working!, sheet }, project: { ...project,
    facts: [...project.facts, { ...text, evidence: text.evidence.map((item) => ({ ...item,
      unitId: `view_${item.sourceId}_${item.unitId}` })) }],
    sources: project.sources.map((source) => ({ ...source, units: source.units.map((unit) =>
      unit.id === `view_${first.sourceId}_${first.unitId}` ? { ...unit,
        representedFactIds: [...unit.representedFactIds, text.id] } : unit) })),
    views: project.views.map((block) => block.id === profile.id ? { ...block,
      state: { ...block.state, text: `${block.state.text}\n${text.value.text}`,
        factIds: [...block.state.factIds, text.id],
        factRevisions: { ...block.state.factRevisions, [text.id]: text.revision } } } : block) } };
  const unit = report(current).units.find((item) => item.unitId === first.unitId)!;
  const warning = report(current).warnings.find((item) =>
    item.code === "TEXT_MEANING" && item.factId === text.id)!;
  assert.equal(unit.id, `view_${first.sourceId}_${first.unitId}`);
  current = editorReducer(current, { type: "coverageDecision", targetKind: "unit", targetId: unit.id,
    disposition: "excluded", reason: "Keep original in the project", dependency: unit.dependency });
  current = editorReducer(current, { type: "coverageAcknowledge", issueId: warning.id,
    dependency: warning.dependency });
  assert.equal(report(current).units.find((item) => item.id === unit.id)?.disposition, "excluded");
  assert.equal(report(current).warnings.find((item) => item.id === warning.id)?.acknowledged, true);
  current = editorReducer(editorReducer(current, { type: "draft", id: profile.id,
    text: "An unrelated profile claim." }), { type: "apply", id: profile.id });
  assert.equal(current.working?.coverage?.decisions.some((item) => item.targetId === unit.id), false);
  assert.equal(current.working?.coverage?.acknowledgments.some((item) => item.issueId === warning.id), false);
  current = editorReducer(current, { type: "undo", id: profile.id });
  assert.equal(report(current).units.find((item) => item.id === unit.id)?.disposition, "excluded");
  assert.equal(report(current).warnings.find((item) => item.id === warning.id)?.acknowledged, true);
});

test("shown confirmation rejects hidden prose and a removed target fact", () => {
  let state = fixture();
  const id = "fact_user_manual_job_recent";
  state = editorReducer(state, { type: "draft", id: "prose_recent", text: "An unrelated project." });
  state = editorReducer(state, { type: "apply", id: "prose_recent" });
  const target = report(state).facts.find((item) => item.id === id)!;
  state = editorReducer(state, { type: "visible", id: "prose_recent" });
  const hidden = report(state).facts.find((item) => item.id === id)!;
  assert.equal(hidden.confirmable, false);
  const refused = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: id,
    disposition: "shown", reason: "A review cannot show hidden prose", dependency: hidden.dependency });
  assert.equal(refused.working?.coverage?.decisions.length ?? 0, 0);
  const project = state.project!;
  const removed = setProject(state, { ...project,
    facts: project.facts.filter((fact) => fact.id !== id),
    employment: project.employment.map((job) => job.id === "recent" ?
      { ...job, factIds: job.factIds.filter((factId) => factId !== id) } : job),
    views: project.views.map((block) => block.id === "prose_recent" ? { ...block,
      state: { ...block.state, factIds: block.state.factIds.filter((factId) => factId !== id),
        factRevisions: Object.fromEntries(Object.entries(block.state.factRevisions)
          .filter(([factId]) => factId !== id)) } } : block) });
  const missing = report(removed).facts.find((item) => item.id === id)!;
  assert.equal(missing.confirmable, false);
  const refusedRemoved = editorReducer(removed, { type: "coverageDecision", targetKind: "fact", targetId: id,
    disposition: "shown", reason: "No current fact", dependency: missing.dependency });
  assert.equal(refusedRemoved.working?.coverage?.decisions.length ?? 0, 0);
  assert.notEqual(target.dependency, hidden.dependency);
});

test("prepare-request validation rejects duplicate and wrong-kind job bindings", () => {
  const state = fixture();
  const duplicate = { ...state, presentation: { ...state.presentation!,
    jobProseBlocks: { recent: "prose_recent", old: "prose_recent" } } };
  assert.ok(report(duplicate).blockers.some((item) => item.code === "BROKEN_JOB_BINDING"));
  const wrongKind = { ...state, presentation: { ...state.presentation!,
    jobProseBlocks: { recent: "profile", old: "prose_old" } } };
  assert.ok(report(wrongKind).blockers.some((item) => item.code === "BROKEN_JOB_BINDING"));
});

test("source integrity catches same-length new and in-place byte changes", async () => {
  const state = fixture();
  const source = state.working!.sources[0]!;
  const originalBytes = new TextEncoder().encode(source.entry.result.units.map((item) => item.text).join(""));
  assert.equal(originalBytes.length, source.entry.result.byteLength);
  const working = { ...state.working!, sources: [{ ...source, originalBytes }] };
  const proof = await verifyWorkingSources(working.sources);
  assert.equal(proof.valid, true);
  const verified = { ...state, working, sourceIntegrity: proof };
  assert.equal(report(verified).blockers.some((item) => item.code === "CORRUPT_DATA" ||
    item.code === "SOURCE_INTEGRITY_PENDING"), false);
  const changedBytes = Uint8Array.from(originalBytes);
  changedBytes[0] = changedBytes[0]! ^ 1;
  const replaced = { ...verified, working: { ...working, sources: [{ ...source, originalBytes: changedBytes }] } };
  assert.ok(report(replaced).blockers.some((item) => item.code === "CORRUPT_DATA"));
  assert.equal((await verifyWorkingSources(replaced.working.sources)).valid, false);
  originalBytes[0] = originalBytes[0]! ^ 1;
  assert.ok(report(verified).blockers.some((item) => item.code === "CORRUPT_DATA"));
});

test("late source proof cannot certify a replaced project opening", async () => {
  const old = fixture();
  const source = old.working!.sources[0]!;
  const bytes = new TextEncoder().encode(source.entry.result.units.map((item) => item.text).join(""));
  const proof = await verifyWorkingSources([{ ...source, originalBytes: bytes }]);
  const next = editorReducer(editorReducer(old, { type: "resetProject" }),
    { type: "loadImported", loadId: "new-opening", ...adaptWorking(old.working!), working: old.working! });
  const ignored = editorReducer(next, { type: "sourceIntegrity", loadId: old.loadId!,
    sources: old.working!.sources, proof });
  assert.equal(ignored.sourceIntegrity, null);
  assert.ok(report(ignored).blockers.some((item) => item.code === "SOURCE_INTEGRITY_PENDING"));
});
