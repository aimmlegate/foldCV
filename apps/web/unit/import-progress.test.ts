import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { elapsedLabel, importProgress, progressMessage } from "../src/workbench/import/progress-state";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";

function response(): RichProjectResponse {
  const workspace: unknown = JSON.parse(readFileSync(new URL("../../../tests/fixtures/rich_workspace.json", import.meta.url), "utf8"));
  assert.ok(validateRichWorkspaceShape(workspace));
  assert.ok(workspace.project);
  const sources = workspace.project.sources;
  return { workspace: { ...workspace, project: null, preDraft: { selectedInput: "file", selectedSourceId: sources[0]?.id ?? null,
    sources, facts: { revision: 1, records: [], tombstones: [] }, operations: [], warnings: [], importDraft: {
      version: 1, runId: "import-current", sourceSha256: "1".repeat(64), skillSha256: "2".repeat(64), sequence: 1,
      profile: { name: "Test Candidate", title: "Platform engineer", location: "", sourceKeys: [] },
      facts: [], blocks: [], receipts: [], finished: false, issues: [],
    } } }, generation: { id: "import-current", status: "running", stage: "normalize_semantics", errorCode: null },
    durability: "durable", savedProjectRevision: 1, savedDocumentRevision: 1, saveError: null };
}

test("processing discoveries show only saved facts from the current import", () => {
  const value = response(), draft = value.workspace.preDraft?.importDraft;
  assert.ok(draft);
  draft.facts = [
    { id: "job", sourceKeys: [], record: { kind: "employment", employer: "Orion", role: "Engineer", periods: [],
      technologies: ["Python", { display: "PostgreSQL", technical: true, experience: "около 3 лет" },
        { display: "Communication", technical: false, experience: "" }] }, text: "" },
    { id: "python", sourceKeys: [], record: { kind: "technology", display: "python", experience: "", technical: true }, text: "" },
    { id: "note", sourceKeys: [], text: "An uncertain relationship needs review." },
  ];
  draft.blocks = [{ id: "experience", kind: "section", category: "experience", region: "main", title: "Опыт", sourceKeys: [] }];
  const snapshot = importProgress(value);
  assert.equal(snapshot.saved, true);
  assert.equal(snapshot.name, "Test Candidate");
  assert.equal(snapshot.facts, 3);
  assert.deepEqual(snapshot.jobs, [{ id: "job", employer: "Orion", role: "Engineer" }]);
  assert.deepEqual(snapshot.technologies, ["Python", "PostgreSQL"]);
  assert.equal(snapshot.sections, 1);
  assert.equal(draft.facts?.[0]?.record?.kind, "employment");
  draft.runId = "previous-import";
  const previous = importProgress(value);
  assert.equal(previous.saved, false);
  assert.equal(previous.facts, 0);
  assert.deepEqual(previous.jobs, []);
  assert.equal(previous.name, "");
});

test("unchanged polls do not invent activity and replacement batches can reduce counts", () => {
  const value = response(), draft = value.workspace.preDraft?.importDraft;
  assert.ok(draft);
  draft.facts = [{ id: "note", sourceKeys: [], text: "Saved source note" }];
  const before = importProgress(value);
  assert.equal(importProgress(structuredClone(value)).stamp, before.stamp);
  draft.sequence = (draft.sequence ?? 0) + 1;
  draft.facts = [];
  const after = importProgress(value);
  assert.notEqual(after.stamp, before.stamp);
  assert.equal(after.facts, 0);
  assert.equal(after.saved, true);
  assert.deepEqual(after.jobs, []);
});

test("source preview counts distinct PDF pages and keeps the displayed excerpt bounded", () => {
  const value = response(), owner = value.workspace.preDraft;
  assert.ok(owner);
  owner.sources = [{ id: "source", revision: 1, originalName: "example.pdf", mimeType: "application/pdf",
    byteRef: "source.pdf", byteSha256: "1".repeat(64), parser: "pdf", parserVersion: "1", warnings: [], overlays: [],
    units: [0, 0, 1].map((index, position) => ({ id: `unit-${String(position)}`, order: position, revision: 1,
      text: "Exact source line ".repeat(40), disposition: "unresolved", representedFactIds: [],
      location: { kind: "page", index, row: null, column: null } })) }];
  owner.selectedSourceId = "source";
  const snapshot = importProgress(value);
  assert.equal(snapshot.pages, 2);
  assert.equal(snapshot.excerpt.length, 360);
  assert.ok(snapshot.excerpt.startsWith("Exact source line"));
});

test("materialized projects keep their actual discoveries while DOCX is prepared", () => {
  const value: unknown = JSON.parse(readFileSync(new URL("../../../tests/fixtures/rich_workspace.json", import.meta.url), "utf8"));
  assert.ok(validateRichWorkspaceShape(value));
  assert.ok(value.project);
  const snapshot = importProgress({ ...response(), workspace: value,
    generation: { id: "import-current", stage: "render", status: "running", errorCode: null } });
  assert.equal(snapshot.saved, true);
  assert.equal(snapshot.facts, value.project.facts.records.length);
  assert.equal(snapshot.jobs.length, value.project.facts.records.filter(record => record.kind === "employment").length);
});

test("waiting copy and elapsed time never invent results or a completion estimate", () => {
  const generation = response().generation;
  assert.ok(generation);
  assert.match(progressMessage({ ...generation, status: "queued" }, false, 50), /очереди/u);
  assert.match(progressMessage(generation, false, 21), /результатов пока нет/u);
  assert.match(progressMessage(generation, true, 21), /Новых сохранений пока нет/u);
  assert.match(progressMessage({ ...generation, stage: "assemble" }, true, 30), /разделам/u);
  assert.match(progressMessage({ ...generation, stage: "render" }, true, 30), /редактируемый файл/u);
  assert.equal(elapsedLabel(3723000), "62:03");
  assert.equal(elapsedLabel(-1000), "0:00");
  assert.equal(elapsedLabel(Number.NaN), "0:00");
});
