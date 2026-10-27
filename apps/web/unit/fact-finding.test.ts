import assert from "node:assert/strict";
import test from "node:test";
import { register } from "node:module";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import type { WorkingFacts } from "../src/contracts/generated/working_facts";
import { employment, facts as synthetic } from "./support/facts";

register(`data:text/javascript,${encodeURIComponent('export async function load(url, context, next) { if (url.includes("/icons.svg")) return { format: "module", source: \'export default "icons.svg"\', shortCircuit: true }; return next(url, context); }')}`, import.meta.url);
const { FactsPanel } = await import("../src/workbench/facts/FactsPanel");

test("fact findings reveal collapsed technologies after the eighth row in their own group", () => {
  const response = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/projects/v7-response.json", import.meta.url), "utf8")) as TemplateProjectResponseV1;
  assert.ok(response.workspace.project);
  const document = response.workspace.project.document, facts = synthetic([employment("job-1")]);
  const field = { value: "Python", rawText: "Python", status: "known", revision: 1, pendingRawText: null, userCorrected: false } as const;
  const technology: Extract<WorkingFacts["records"][number], { kind: "technology" }> = { id: "tech-base", kind: "technology",
    revision: 1, origin: "user", evidence: [], userCorrected: false, jobId: null, subprojectId: null, display: field,
    canonicalId: { ...field, value: "python", rawText: "python" }, experience: { ...field, value: "", rawText: "" } };
  facts.records = facts.records.filter(record => record.kind !== "technology");
  for (const jobId of [null, "job-1"]) for (let index = 0; index < 10; index++) {
    const copy = structuredClone(technology); copy.id = `tech-${jobId ?? "global"}-${index}`; copy.jobId = jobId;
    facts.records.push(copy);
  }
  const props = { facts, document, submit: async () => {}, pending: [], paused: false, hidden: false, close: () => {} };
  const collapsed = renderToStaticMarkup(createElement(FactsPanel, props));
  assert.ok(!collapsed.includes('data-fact-id="tech-global-9"'));
  for (const recordId of ["tech-global-9", "tech-job-1-9"]) {
    const focused = renderToStaticMarkup(createElement(FactsPanel, { ...props, focusRequest: { recordId } }));
    assert.ok(focused.includes(`data-fact-id="${recordId}"`));
    const other = recordId === "tech-global-9" ? "tech-job-1-9" : "tech-global-9";
    assert.ok(!focused.includes(`data-fact-id="${other}"`));
  }
});
