import assert from "node:assert/strict";
import { test } from "node:test";
import { editorReducer, initialEditorState } from "../src/editor/state";
import type { EditorState } from "../src/editor/state";
import { exportReadiness } from "../src/preview/readiness";
import type { Facts } from "../src/contracts/generated/project";

function example(): EditorState {
  return editorReducer(initialEditorState, { type: "loadExample", loadId: "readiness-example" });
}

function acknowledgeAll(state: EditorState): EditorState {
  let current = state;
  for (const warning of exportReadiness(state).unacknowledged)
    current = editorReducer(current, { type: "coverageAcknowledge", issueId: warning.id,
      dependency: warning.dependency });
  return current;
}

test("final export needs current concrete warning review while preview remains available", () => {
  let state = example();
  assert.equal(exportReadiness(state).blockers.length, 0);
  assert.equal(exportReadiness(state).allowed, false);
  state = acknowledgeAll(state);
  assert.equal(exportReadiness(state).allowed, true);
  state = editorReducer(state, { type: "structuredDraft", key: "migration:language", text: "ru" });
  assert.equal(exportReadiness(state).pendingInput, true);
  assert.equal(exportReadiness(state).allowed, false);
  state = editorReducer(state, { type: "structuredCancel", key: "migration:language" });
  state = editorReducer(state, { type: "presentationDraft", field: "title", text: "Different title" });
  assert.equal(exportReadiness(state).pendingInput, true);
  state = editorReducer(state, { type: "presentationCancel", field: "title" });
  assert.equal(exportReadiness(state).allowed, true);
  state = editorReducer(state, { type: "draft", id: "job_1_prose", text: "Changed the metric context." });
  assert.equal(exportReadiness(state).pendingInput, true);
  assert.equal(exportReadiness(state).allowed, false);
  state = editorReducer(state, { type: "apply", id: "job_1_prose" });
  assert.equal(exportReadiness(state).pendingInput, false);
  assert.equal(exportReadiness(state).allowed, false);
  assert.ok(exportReadiness(state).unacknowledged.some((item) => item.code === "METRIC_MEANING"));
  state = acknowledgeAll(state);
  assert.equal(exportReadiness(state).allowed, true);
  state = editorReducer(state, { type: "undo", id: "job_1_prose" });
  assert.equal(exportReadiness(state).allowed, true);
});

test("a broken job binding remains blocked after every warning is acknowledged", () => {
  let state = acknowledgeAll(example());
  const project = state.project!;
  state = { ...state, presentation: { ...state.presentation!, jobProseBlocks: { job_1: "job_2_prose" } } };
  const readiness = exportReadiness(state);
  assert.equal(readiness.allowed, false);
  assert.ok(readiness.blockers.some((issue) => issue.code === "BROKEN_JOB_BINDING"));
  assert.equal(project.projectId, state.project?.projectId);
});

test("standalone essential fact needs a reasoned current disposition", () => {
  let state = example();
  const project = state.project!;
  const prose = project.views.find((item) => item.id === "job_1_prose")!;
  state = { ...state, project: { ...project, views: project.views.map((item) => item.id === prose.id ?
    { ...item, state: { ...item.state, factIds: [], factRevisions: {} } } : item) } };
  const missing = exportReadiness(state).blockers.find((item) => item.code === "MISSING_ESSENTIAL");
  assert.ok(missing?.factId);
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: missing.factId,
    disposition: "excluded", reason: "", dependency: missing.dependency });
  assert.ok(exportReadiness(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL"));
  state = editorReducer(state, { type: "coverageDecision", targetKind: "fact", targetId: missing.factId,
    disposition: "excluded", reason: "Not in this selected view", dependency: missing.dependency });
  assert.equal(exportReadiness(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL"), false);
  assert.equal(state.standaloneDecisions[0]?.reason, "Not in this selected view");
  state = editorReducer(state, { type: "draft", id: prose.id, text: "Another selected description." });
  state = editorReducer(state, { type: "apply", id: prose.id });
  assert.equal(state.standaloneDecisions.length, 0);
  state = editorReducer(state, { type: "undo", id: prose.id });
  assert.equal(state.standaloneDecisions[0]?.reason, "Not in this selected view");
  assert.equal(exportReadiness(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL"), false);
});

test("literal candidate identity represents only a global fact and its review expires on identity edit", () => {
  let state = example();
  const identity: Extract<Facts[number], { kind: "text" }> = {
    id: "fact_identity_literal", revision: 1, kind: "text", value: { text: state.presentation!.name },
    evidence: [], origin: "user", importance: "essential", jobId: null, subprojectId: null,
  };
  state = { ...state, project: { ...state.project!, facts: [...state.project!.facts, identity] } };
  const first = exportReadiness(state);
  assert.equal(first.review?.facts.find((item) => item.id === identity.id)?.disposition, "shown");
  assert.equal(first.blockers.some((item) => item.factId === identity.id), false);
  const meaning = first.unacknowledged.find((item) => item.factId === identity.id && item.code === "TEXT_MEANING");
  assert.ok(meaning);
  state = editorReducer(state, { type: "coverageAcknowledge", issueId: meaning.id,
    dependency: meaning.dependency });
  state = editorReducer(state, { type: "presentationDraft", field: "title", text: "Unrelated title" });
  state = editorReducer(state, { type: "presentationApply", field: "title" });
  assert.equal(state.standaloneAcknowledgments.some((item) => item.issueId === meaning.id), true);
  assert.equal(exportReadiness(state).review?.warnings.find((item) => item.id === meaning.id)?.acknowledged, true);
  state = editorReducer(state, { type: "presentationDraft", field: "name", text: "Changed Identity" });
  state = editorReducer(state, { type: "presentationApply", field: "name" });
  assert.equal(state.standaloneAcknowledgments.some((item) => item.issueId === meaning.id), false);
  assert.ok(exportReadiness(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL" &&
    item.factId === identity.id));
  const jobOnly = { ...identity, id: "fact_job_identity_literal", jobId: "job_1" };
  state = { ...state, project: { ...state.project!, facts: [...state.project!.facts, jobOnly] } };
  assert.ok(exportReadiness(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL" &&
    item.factId === jobOnly.id));
});

test("title identity review survives a name edit but expires on title edit", () => {
  let state = example();
  const identity: Extract<Facts[number], { kind: "text" }> = {
    id: "fact_title_literal", revision: 1, kind: "text", value: { text: state.presentation!.title },
    evidence: [], origin: "user", importance: "essential", jobId: null, subprojectId: null,
  };
  state = { ...state, project: { ...state.project!, facts: [...state.project!.facts, identity] } };
  const meaning = exportReadiness(state).unacknowledged.find((item) =>
    item.factId === identity.id && item.code === "TEXT_MEANING");
  assert.ok(meaning);
  state = editorReducer(state, { type: "coverageAcknowledge", issueId: meaning.id,
    dependency: meaning.dependency });
  state = editorReducer(state, { type: "presentationDraft", field: "name", text: "Unrelated name" });
  state = editorReducer(state, { type: "presentationApply", field: "name" });
  assert.equal(exportReadiness(state).review?.warnings.find((item) => item.id === meaning.id)?.acknowledged, true);
  state = editorReducer(state, { type: "presentationDraft", field: "title", text: "Changed title" });
  state = editorReducer(state, { type: "presentationApply", field: "title" });
  assert.equal(state.standaloneAcknowledgments.some((item) => item.issueId === meaning.id), false);
  assert.ok(exportReadiness(state).blockers.some((item) => item.code === "MISSING_ESSENTIAL" &&
    item.factId === identity.id));
});
