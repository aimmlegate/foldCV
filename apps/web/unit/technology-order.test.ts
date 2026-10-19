import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import type { WorkspaceV6 } from "../src/contracts/generated/workspace_v6";
import type { WorkingFacts } from "../src/contracts/generated/working_facts";
import { adjacentTechnology, documentTechnologies } from "../src/rich/technology-order";
import { currentPanelIntent } from "../src/rich/panel-intents";
import { documentCells } from "../src/rich/document-cells";

function fixture() {
  const workspace = JSON.parse(readFileSync(new URL("../../../tests/fixtures/rich_workspace.json", import.meta.url), "utf8")) as WorkspaceV6;
  const project = workspace.project;
  assert.ok(project);
  return project;
}

function technology(id: string, display: string, jobId: string | null = null): Extract<WorkingFacts["records"][number], { kind: "technology" }> {
  return { id, revision: 1, kind: "technology", origin: "user", evidence: [], userCorrected: true, jobId, subprojectId: null,
    display: { value: display, rawText: display, status: "known", revision: 1, pendingRawText: null },
    canonicalId: { value: null, rawText: "", status: "unknown", revision: 1, pendingRawText: null } };
}

test("keyboard moves work at both edges and can place an item last", () => {
  assert.equal(adjacentTechnology(["a", "b", "c"], "a", -1), undefined);
  assert.equal(adjacentTechnology(["a", "b", "c"], "a", 1), "c");
  assert.equal(adjacentTechnology(["a", "b", "c"], "b", 1), null);
  assert.equal(adjacentTechnology(["a", "b", "c"], "c", 1), undefined);
  assert.equal(adjacentTechnology(["a", "b", "c"], "c", -1), "b");
  assert.equal(adjacentTechnology(["a", "b", "c"], "removed", 1), undefined);
});

test("facts follow authored main text order while Focus stays separate", () => {
  const project = fixture();
  const records = ["SQL", "Python", "Docker"].map((display, index) => technology(`tool-${index}`, display));
  project.facts.records = records;
  const block = project.document.regions[0]?.blocks.find(block => Array.isArray(block.content) && block.content.some(span => span.type === "fact_field"));
  assert.ok(block && Array.isArray(block.content));
  const field = block.content.find(span => span.type === "fact_field");
  assert.ok(field?.type === "fact_field");
  const paragraph = { id: "ordered-tools", revision: 1, type: "paragraph" as const, props: {}, children: [], provenance: [],
    content: [2, 0, 1].map(index => ({ ...field, bindingId: `binding-${index}`, fieldKey: "display", recordId: `tool-${index}`, text: "tool" })) };
  project.document.regions.forEach(region => { region.blocks = region.role === "main" ? [paragraph] : []; });
  assert.deepEqual(documentTechnologies(project.facts, project.document, null).map(record => record.display.rawText), ["Docker", "SQL", "Python"]);
  assert.deepEqual(project.facts.records.filter(record => record.kind === "technology").map(record => record.display.rawText), ["SQL", "Python", "Docker"]);
});

test("queued moves reject missing targets and another job without changing scope", () => {
  const project = fixture();
  project.facts.records = [technology("a", "Python"), technology("b", "Python", "another-job")];
  assert.throws(() => currentPanelIntent({ operation: "move_technology", recordId: "a", beforeRecordId: "removed" }, project.facts));
  assert.throws(() => currentPanelIntent({ operation: "move_technology", recordId: "a", beforeRecordId: "b" }, project.facts));
  assert.equal(currentPanelIntent({ operation: "move_technology", recordId: "a", beforeRecordId: "a" }, project.facts), null);
  assert.deepEqual(currentPanelIntent({ operation: "move_technology", recordId: "a", beforeRecordId: null }, project.facts),
    { operation: "move_technology", recordId: "a", beforeRecordId: null });
});

test("manual Focus order is part of the same durable history cell", () => {
  const project = fixture();
  const section = project.document.regions.flatMap(region => region.blocks).find(block => block.type === "section");
  assert.ok(section?.type === "section");
  const before = documentCells(project.document, new Map()).get(`block:${section.id}`);
  section.props.manualOrder = true;
  const after = documentCells(project.document, new Map()).get(`block:${section.id}`);
  assert.notEqual(after, before);
  assert.match(after ?? "", /"manualOrder":true/u);
});
