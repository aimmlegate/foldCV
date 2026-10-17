import assert from "node:assert/strict";
import test from "node:test";
import { Fragment, Schema, Slice } from "@tiptap/pm/model";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { allowsBasicEdit, basicPastedSlice } from "../src/rich/basic-editing";
import { changePrecision, datePrecision, dateText } from "../src/workbench/facts/dates";
import { technologyCatalog, technologySuggestions } from "../src/workbench/facts/technology-catalog";
import { technologyKey } from "../src/rich/panel-intents";
import type { WorkingFieldPartialDate } from "../src/contracts/generated/working_facts";
import { noticeText } from "../src/workbench/ui/notice-text";
import { panelHarness } from "./rich-panel-harness";

function facts() {
  const value: unknown = structuredClone(fixture);
  assert.ok(validateRichWorkspaceShape(value)); assert.ok(value.project);
  return value.project.facts;
}
const date = (value: WorkingFieldPartialDate["value"], rawText = "source date"): WorkingFieldPartialDate => ({
  value, rawText, status: value ? "known" : "unresolved", revision: 1, pendingRawText: null,
});

test("date controls display exact known precision without exposing serialized source objects", () => {
  assert.equal(dateText(date({ precision: "year", year: 2019, month: null, day: null })), "2019");
  assert.equal(dateText(date({ precision: "month", year: 2024, month: 2, day: null })), "2024-02");
  assert.equal(dateText(date({ precision: "day", year: 2024, month: 2, day: 29 })), "2024-02-29");
  assert.equal(dateText(date(null, "весна 2020")), "весна 2020");
  assert.equal(dateText({ ...date({ precision: "year", year: 2020, month: null, day: null }, "около 2020"), status: "pending" }), "около 2020");
});

test("refining date precision requires a choice and never invents a month or day", () => {
  assert.equal(changePrecision("2020", "month"), "");
  assert.equal(changePrecision("2020-02", "day"), "");
  assert.equal(changePrecision("2024-02-29", "year"), "2024");
  assert.equal(changePrecision("2024-02-29", "month"), "2024-02");
  assert.equal(changePrecision("около 2020", "text"), "около 2020");
  assert.equal(changePrecision("около 2020", "year"), "");
  assert.equal(datePrecision("2020-02-01"), "day");
  assert.equal(datePrecision("2020"), "year");
  assert.equal(datePrecision("2020-02"), "month");
  assert.equal(datePrecision("весна 2020"), "text");
});

test("picker values use the real facts path, preserve precision and share Undo/Redo", async () => {
  const h = panelHarness();
  try {
    const job = h.facts().records.find(record => record.kind === "employment"); assert.ok(job?.kind === "employment");
    const period = job.periods[0]; assert.ok(period);
    const before = structuredClone(period);
    await h.intents.enqueue({ operation: "edit", recordId: job.id, values: { [`period:${period.id}:start`]: "2020", [`period:${period.id}:end`]: "2024-02-29" } });
    const current = () => { const record = h.facts().records.find(record => record.id === job.id); assert.ok(record?.kind === "employment"); const p = record.periods[0]; assert.ok(p); return p; };
    assert.deepEqual(current().start.value, { precision: "year", year: 2020, month: null, day: null });
    assert.deepEqual(current().end.value, { precision: "day", year: 2024, month: 2, day: 29 });
    assert.ok(h.history.undo()); assert.deepEqual(current(), before);
    assert.ok(h.history.redo()); assert.equal(current().end.rawText, "2024-02-29");
    await h.queue.flush();
  } finally { h.close(); }
});

test("the embedded catalog spans major technical roles and contains no case duplicates", () => {
  for (const name of ["TypeScript", "Python", "PostgreSQL", "Kubernetes", "Swift", "Playwright", "PyTorch", "1С:Предприятие", "Figma", "ROS 2", "Burp Suite"])
    assert.ok(technologyCatalog.includes(name));
  assert.equal(new Set(technologyCatalog.map(technologyKey)).size, technologyCatalog.length);
});

test("project and role mentions outrank unrelated technologies without leaking another job's context", () => {
  const value = facts(), job = value.records.find(record => record.kind === "employment"); assert.ok(job?.kind === "employment");
  job.role.rawText = "Backend engineer: Golang and PostgreSQL services";
  value.records.push({ ...structuredClone(job), id: "other-job", role: { ...job.role, rawText: "Unity game developer" } });
  const choices = technologySuggestions(value, job.id, "");
  assert.ok(choices.indexOf("Go") < choices.indexOf("Unity"));
  assert.ok(choices.indexOf("PostgreSQL") < choices.indexOf("Unity"));
  assert.ok(choices.indexOf("FastAPI") < choices.indexOf("Unity"));
});

test("technology searches support aliases and keep custom imported names", () => {
  const value = facts();
  assert.ok(technologySuggestions(value, null, "k8s").includes("Kubernetes"));
  assert.ok(technologySuggestions(value, null, "csharp").includes("C#"));
  assert.ok(technologySuggestions(value, null, "питон").includes("Python"));
  const field = { value: "Internal platform", rawText: "Internal platform", status: "known" as const, revision: 1, pendingRawText: null };
  value.records.push({ id: "custom-tech", kind: "technology", revision: 1, origin: "user", userCorrected: true, evidence: [],
    jobId: null, subprojectId: null, canonicalId: { ...field }, display: { ...field } });
  assert.deepEqual(technologySuggestions(value, null, "internal"), ["Internal platform"]);
});

const schema = new Schema({ nodes: { doc: { content: "blockContainer+" },
  blockContainer: { content: "(paragraph|quote|codeBlock|table|checkListItem|toggleListItem)", attrs: { id: { default: "" } } },
  paragraph: { content: "inline*" }, quote: { content: "inline*" }, codeBlock: { content: "inline*" },
  checkListItem: { content: "inline*" }, toggleListItem: { content: "inline*" },
  table: { content: "tableRow+" }, tableRow: { content: "tableCell+" }, tableCell: { content: "paragraph+" }, text: { group: "inline" } },
  marks: { bold: {} } });
const block = (id: string, type: string, text: string) => schema.node("blockContainer", { id }, schema.node(type, null, schema.text(text)));

test("legacy rich blocks remain editable and movable while new restricted blocks are denied", () => {
  const old = schema.node("doc", null, [block("old-code", "codeBlock", "old"), block("text", "paragraph", "text")]);
  const edited = schema.node("doc", null, [block("text", "paragraph", "new"), block("old-code", "codeBlock", "edited")]);
  assert.equal(allowsBasicEdit(old, edited), true);
  for (const type of ["quote", "codeBlock", "checkListItem", "toggleListItem"]) {
    const added = schema.node("doc", null, [...old.content.content, block("new", type, "new")]);
    assert.equal(allowsBasicEdit(old, added), false);
  }
  assert.equal(allowsBasicEdit(old, schema.node("doc", null, [...old.content.content, block("old-code", "codeBlock", "duplicate")])), false);
});

test("pasted quotes and code become ordinary styled text and retain all authored content", () => {
  const quote = schema.node("blockContainer", { id: "paste" }, schema.node("quote", null, schema.text("Quoted text", [schema.mark("bold")])));
  const code = block("code", "codeBlock", "line one\nline two");
  const result = basicPastedSlice(new Slice(Fragment.fromArray([quote, code]), 0, 0));
  assert.equal(result.openStart, 0); assert.equal(result.openEnd, 0);
  assert.equal(result.content.child(0).firstChild?.type.name, "paragraph");
  assert.equal(result.content.child(0).firstChild?.firstChild?.marks[0]?.type.name, "bold");
  assert.equal(result.content.child(1).textContent, "line one\nline two");
  assert.ok(schema.nodes["doc"]?.validContent(result.content));
});

test("pasted tables retain every cell's text as paragraphs without enabling table creation", () => {
  const table = schema.node("table", null, ["first", "second"].map(text => schema.node("tableRow", null,
    schema.node("tableCell", null, schema.node("paragraph", null, schema.text(text))))));
  const result = basicPastedSlice(new Slice(Fragment.from(schema.node("blockContainer", { id: "table-paste" }, table)), 0, 0));
  assert.equal(result.content.firstChild?.firstChild?.type.name, "paragraph");
  assert.ok(result.content.textBetween(0, result.content.size).includes("first"));
  assert.ok(result.content.textBetween(0, result.content.size).includes("second"));
  assert.ok(schema.nodes["doc"]?.validContent(result.content));
});

test("editor notices keep useful messages and replace internal recovery or transport codes", () => {
  assert.equal(noticeText("Выберите PNG, JPEG или WebP"), "Выберите PNG, JPEG или WebP");
  for (const value of ["JOB_SCOPE_INVALID", "DRAFT_STORAGE_FAILED", "WRITER_UNKNOWN", "OUTCOME_UNKNOWN"])
    assert.ok(noticeText(value).includes("черновик"));
  assert.ok(!noticeText("IMAGE_SESSION_STALE").includes("IMAGE_SESSION_STALE"));
  assert.ok(!noticeText("Failed to fetch").includes("Failed to fetch"));
});

test("technology ranking reads the owned project description without using a peer project's text", () => {
  const value: unknown = structuredClone(fixture); assert.ok(validateRichWorkspaceShape(value)); assert.ok(value.project);
  const facts = value.project.facts, job = facts.records.find(record => record.kind === "employment"); assert.ok(job?.kind === "employment");
  const main = value.project.document.regions[2];
  main.blocks = [{ id: "owned-description", revision: 1, type: "section", props: { recordId: job.id }, content: [], provenance: [], children: [
    { id: "description", revision: 1, type: "paragraph", props: { alignment: "left" }, provenance: [], children: [], content: [{ type: "text", text: "Built the service using Qdrant and FastAPI.", styles: {} }] },
  ] }, { id: "peer-description", revision: 1, type: "section", props: { recordId: "other-job" }, content: [], provenance: [], children: [
    { id: "peer-text", revision: 1, type: "paragraph", props: { alignment: "left" }, provenance: [], children: [], content: [{ type: "text", text: "Created Unity games.", styles: {} }] },
  ] }];
  const choices = technologySuggestions(facts, job.id, "", value.project.document);
  assert.ok(choices.indexOf("Qdrant") < choices.indexOf("Unity"));
  assert.ok(choices.indexOf("FastAPI") < choices.indexOf("Unity"));
});
