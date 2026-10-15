import assert from "node:assert/strict";
import test from "node:test";
import { importView, reviewId } from "../src/workbench/import/view";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import { readFileSync } from "node:fs";

function response(): RichProjectResponse {
  const value: unknown = JSON.parse(readFileSync(new URL("../../../tests/fixtures/rich_workspace.json", import.meta.url), "utf8"));
  assert.ok(validateRichWorkspaceShape(value));
  return { workspace: value, generation: null, durability: "durable", savedProjectRevision: 1, savedDocumentRevision: 1, saveError: null };
}

test("assembly cannot open an editable document while its generation is still running", () => {
  const value = response();
  const running = { ...value, generation: { id: "generation-1", status: "running" as const, stage: "render" as const, errorCode: null } };
  assert.equal(importView(running, null, false), "progress");
  assert.equal(importView(running, null, true), "progress");
});

test("review and source return preserve a completed result without starting generation", () => {
  const value = response();
  const completed = { ...value, generation: { id: "generation-1", status: "completed" as const, stage: "render" as const, errorCode: null } };
  assert.equal(importView(completed, null, false), "assessment");
  assert.equal(importView(completed, reviewId(completed), false), "editor");
  assert.equal(importView(completed, reviewId(completed), true), "source");
  const failedExport = { ...completed, generation: { ...completed.generation, status: "failed" as const, errorCode: "RENDER_FAILED" } };
  assert.equal(importView(failedExport, null, false), "assessment");
  assert.equal(importView(failedExport, reviewId(failedExport), false), "editor");
});
