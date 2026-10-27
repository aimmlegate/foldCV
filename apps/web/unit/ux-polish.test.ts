import assert from "node:assert/strict";
import test from "node:test";
import { changePrecision, datePrecision, dateText } from "../src/workbench/facts/dates";
import { technologyCatalog, technologySuggestions } from "../src/workbench/facts/technology-catalog";
import { technologyKey } from "../src/rich/panel-intents";
import type { WorkingFieldPartialDate } from "../src/contracts/generated/working_facts";
import { noticeText } from "../src/workbench/ui/notice-text";
import { facts } from "./support/facts";
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

test("editor notices keep useful messages and replace internal recovery or transport codes", () => {
  assert.equal(noticeText("Выберите PNG, JPEG или WebP"), "Выберите PNG, JPEG или WebP");
  for (const [code, description] of [["JOB_SCOPE_INVALID", /фоновую задачу/u], ["DRAFT_STORAGE_FAILED", /черновик/u],
    ["WRITER_UNKNOWN", /редактор/u], ["OUTCOME_UNKNOWN", /Сохранение пока не подтверждено/u]] as const) {
    assert.match(noticeText(code), description);
    assert.ok(!noticeText(code).includes(code));
  }
  assert.ok(!noticeText("IMAGE_SESSION_STALE").includes("IMAGE_SESSION_STALE"));
  assert.ok(!noticeText("Failed to fetch").includes("Failed to fetch"));
});

test("technology ranking reads the owned project description without using a peer project's text", () => {
  const value = facts(), job = value.records.find(record => record.kind === "employment"); assert.ok(job?.kind === "employment");
  const main = { role: "main", blocks: [{ id: "owned-description", revision: 1, type: "section", props: { recordId: job.id }, content: [], provenance: [], children: [
    { id: "description", revision: 1, type: "paragraph", props: { alignment: "left" }, provenance: [], children: [], content: [{ type: "text", text: "Built the service using Qdrant and FastAPI.", styles: {} }] },
  ] }, { id: "peer-description", revision: 1, type: "section", props: { recordId: "other-job" }, content: [], provenance: [], children: [
    { id: "peer-text", revision: 1, type: "paragraph", props: { alignment: "left" }, provenance: [], children: [], content: [{ type: "text", text: "Created Unity games.", styles: {} }] },
  ] }] };
  const choices = technologySuggestions(value, job.id, "", { regions: [main] });
  assert.ok(choices.indexOf("Qdrant") < choices.indexOf("Unity"));
  assert.ok(choices.indexOf("FastAPI") < choices.indexOf("Unity"));
});
