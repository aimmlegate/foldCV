import assert from "node:assert/strict";
import { test } from "node:test";
import { validateContract } from "../src/contracts/validate";
import { draftFor, editableFactValue, editorReducer, hasUnappliedDraft, initialEditorState, renderStale } from "../src/editor/state";
import type { EditorState } from "../src/editor/state";

function loaded(): EditorState { return editorReducer(initialEditorState, { type: "loadExample" }); }
function block(state: EditorState, id: string) {
  const found = state.project?.views.find((item) => item.id === id);
  assert.ok(found);
  return found;
}

test("explicit example starts with no operations and a valid project", () => {
  assert.equal(initialEditorState.project, null);
  const input = editorReducer(initialEditorState, { type: "sourceText", text: "Draft source" });
  const state = editorReducer(input, { type: "loadExample" });
  assert.equal(state.project?.operations.length, 0);
  assert.equal(state.sourceText, "Draft source");
  assert.ok(validateContract("project", state.project));
  assert.equal(state.stage, "editor");
});

test("draft survives navigation and apply rejects blank text", () => {
  let state = loaded();
  state = editorReducer(state, { type: "draft", id: "profile", text: "New profile" });
  state = editorReducer(state, { type: "select", id: "focus" });
  assert.equal(draftFor(state, block(state, "profile")), "New profile");
  assert.ok(hasUnappliedDraft(state));
  assert.equal(block(state, "profile").state.text, "Engineer with service experience.");
  state = editorReducer(state, { type: "draft", id: "profile", text: "  " });
  state = editorReducer(state, { type: "apply", id: "profile" });
  assert.equal(state.errors.profile, "Введите текст блока.");
  assert.equal(block(state, "profile").revision, 2);
  state = editorReducer(state, { type: "cancel", id: "profile" });
  assert.equal(state.errors.profile, "");
  assert.equal(draftFor(state, block(state, "profile")), "Engineer with service experience.");
});

test("accepted edit locks only its block and undo restores provenance and review", () => {
  let state = loaded();
  state = editorReducer(state, { type: "review", id: "job_1_prose" });
  const before = block(state, "job_1_prose");
  const other = block(state, "focus");
  state = editorReducer(state, { type: "draft", id: "job_1_prose", text: "Edited project" });
  state = editorReducer(state, { type: "apply", id: "job_1_prose" });
  const applied = block(state, "job_1_prose");
  assert.equal(applied.state.text, "Edited project");
  assert.equal(applied.state.origin, "manual");
  assert.equal(applied.state.locked, true);
  assert.equal(applied.revision, before.revision + 1);
  assert.equal(block(state, "focus"), other);
  assert.equal(state.project?.review.decisions.filter((decision) => decision.targetId === "job_1_prose").length, 0);
  state = editorReducer(state, { type: "undo", id: "job_1_prose" });
  const restored = block(state, "job_1_prose");
  assert.deepEqual(restored.state, before.state);
  assert.equal(restored.revision, applied.revision + 1);
  assert.equal(state.project?.review.decisions.find((decision) => decision.targetId === "job_1_prose")?.targetRevision, restored.revision);
  assert.ok(validateContract("project", state.project));
});

test("visibility and lock revisions rise; undo restores last accepted action", () => {
  let state = loaded();
  const initial = block(state, "focus");
  state = editorReducer(state, { type: "visible", id: "focus" });
  assert.equal(block(state, "focus").visible, false);
  assert.equal(block(state, "focus").state.text, initial.state.text);
  state = editorReducer(state, { type: "lock", id: "focus" });
  assert.equal(block(state, "focus").state.locked, true);
  state = editorReducer(state, { type: "undo", id: "focus" });
  assert.equal(block(state, "focus").state.locked, false);
  assert.equal(block(state, "focus").visible, false);
  assert.equal(block(state, "focus").state.text, initial.state.text);
  assert.ok(block(state, "focus").revision > initial.revision);
});

test("fact correction invalidates dependent blocks and old review cannot return on undo", () => {
  let state = loaded();
  state = editorReducer(state, { type: "review", id: "job_1_prose" });
  state = editorReducer(state, { type: "draft", id: "job_1_prose", text: "Manual project" });
  state = editorReducer(state, { type: "apply", id: "job_1_prose" });
  state = editorReducer(state, { type: "fact", id: "fact_metric", value: "2500" });
  assert.equal(state.project?.facts.find((fact) => fact.id === "fact_metric")?.revision, 3);
  assert.equal(block(state, "job_1_prose").status, "stale");
  assert.equal(block(state, "profile").status, "stale");
  assert.equal(block(state, "focus").status, "ready");
  state = editorReducer(state, { type: "undo", id: "job_1_prose" });
  assert.equal(block(state, "job_1_prose").status, "stale");
  assert.equal(state.project?.review.decisions.some((decision) => decision.targetId === "job_1_prose"), false);
  assert.ok(validateContract("project", state.project));
});

test("invalid fact input preserves revisions and a later valid edit makes render stale", () => {
  let state = loaded();
  const project = state.project;
  assert.ok(project);
  const render = project.renders[0];
  assert.ok(render);
  const withPdf: EditorState = { ...state, project: { ...project, renders: [{ ...render, pdf: { path: "renders/demo.pdf", sha256: "a".repeat(64), size: 10 } }] } };
  assert.equal(renderStale(withPdf.project!), false);
  state = editorReducer(withPdf, { type: "fact", id: "fact_metric", value: "bad" });
  assert.equal(state.errors.fact_metric, "Введите корректное значение факта.");
  assert.equal(state.project?.revision, project.revision);
  state = editorReducer(state, { type: "fact", id: "fact_metric", value: "3000" });
  assert.equal(state.project?.revision, project.revision + 1);
  assert.ok(state.project && renderStale(state.project));
});

test("explicit apply after a fact change refreshes dependencies before review", () => {
  let state = loaded();
  state = editorReducer(state, { type: "fact", id: "fact_metric", value: "2600" });
  assert.equal(block(state, "job_1_prose").status, "stale");
  state = editorReducer(state, { type: "apply", id: "job_1_prose" });
  assert.equal(block(state, "job_1_prose").status, "ready");
  assert.equal(block(state, "job_1_prose").state.factRevisions.fact_metric, 3);
  state = editorReducer(state, { type: "review", id: "job_1_prose" });
  assert.equal(state.project?.review.decisions.some((decision) => decision.targetId === "job_1_prose"), true);
  assert.ok(validateContract("project", state.project));
});

test("example reload cannot replace an open edited project", () => {
  let state = loaded();
  state = editorReducer(state, { type: "draft", id: "job_1_prose", text: "Accepted" });
  state = editorReducer(state, { type: "apply", id: "job_1_prose" });
  state = editorReducer(state, { type: "draft", id: "job_1_prose", text: "Pending" });
  const unchanged = editorReducer(state, { type: "loadExample" });
  assert.equal(unchanged, state);
  assert.equal(block(unchanged, "job_1_prose").state.text, "Accepted");
  assert.equal(draftFor(unchanged, block(unchanged, "job_1_prose")), "Pending");
  assert.ok(unchanged.undo.job_1_prose);
});

test("undo accepted edit keeps a newer unapplied draft", () => {
  let state = loaded();
  const original = block(state, "job_1_prose").state.text;
  state = editorReducer(state, { type: "draft", id: "job_1_prose", text: "Accepted" });
  state = editorReducer(state, { type: "apply", id: "job_1_prose" });
  state = editorReducer(state, { type: "draft", id: "job_1_prose", text: "New pending text" });
  state = editorReducer(state, { type: "undo", id: "job_1_prose" });
  assert.equal(block(state, "job_1_prose").state.text, original);
  assert.equal(draftFor(state, block(state, "job_1_prose")), "New pending text");
  assert.ok(hasUnappliedDraft(state));
  state = editorReducer(state, { type: "cancel", id: "job_1_prose" });
  assert.equal(draftFor(state, block(state, "job_1_prose")), original);
});

test("equivalent metric input clears draft without revision or review changes", () => {
  let state = loaded();
  state = editorReducer(state, { type: "review", id: "job_1_prose" });
  const project = state.project;
  assert.ok(project);
  state = editorReducer(state, { type: "factDraft", id: "fact_metric", text: "02000" });
  state = editorReducer(state, { type: "fact", id: "fact_metric", value: "02000" });
  assert.equal(state.project, project);
  assert.equal(state.factDrafts.fact_metric, undefined);
  assert.equal(state.project?.facts.find((fact) => fact.id === "fact_metric")?.revision, 2);
  assert.equal(block(state, "job_1_prose").status, "ready");
  assert.equal(state.project?.review.decisions.some((decision) => decision.targetId === "job_1_prose"), true);
});

test("technology fact cannot be changed through generic text actions", () => {
  let state = loaded();
  const project = state.project;
  assert.ok(project);
  const technology = project.facts.find((fact) => fact.id === "fact_tech");
  assert.ok(technology);
  assert.equal(editableFactValue(technology), null);
  state = editorReducer(state, { type: "factDraft", id: "fact_tech", text: "Rust" });
  assert.equal(state.factDrafts.fact_tech, undefined);
  state = editorReducer(state, { type: "fact", id: "fact_tech", value: "Rust" });
  assert.equal(state.project, project);
  assert.equal(technology.kind, "technology");
  if (technology.kind === "technology") {
    assert.equal(technology.value.canonicalId, "python");
    assert.equal(technology.value.display, "Python");
  }
  assert.ok(validateContract("project", state.project));
});
