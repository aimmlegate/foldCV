import assert from "node:assert/strict";
import test from "node:test";
import { validateBackgroundShape } from "../src/contracts/background-validate";
import { statusLabel, summary } from "../src/background/status";
import { job } from "./support/background-writer";

test("browser validation accepts the server import submission and rejects incomplete tool sets", () => {
  const model = job.submission.models[0]; assert.ok(model);
  const submission = { ...structuredClone(job.submission), kind: "processing", schedulingClass: "background",
    input: { ...job.submission.input, kind: "processing" }, models: [{ ...model, stage: "extraction" }],
    tools: ["read_import", "save_import", "finish_import"], allowEdits: true, allowWeb: false };
  assert.equal(validateBackgroundShape("background_submission_v1", submission), true);
  assert.equal(validateBackgroundShape("background_submission_v1", { ...submission, tools: submission.tools.slice(1) }), false);
  assert.equal(validateBackgroundShape("background_submission_v1", { ...submission, allowWeb: true }), false);
  assert.equal(validateBackgroundShape("background_submission_v1", { ...submission, models: [{ ...model, stage: "assessment" }] }), false);
});

test("failed execution remains visible when a proposal is ready for publication", () => {
  const value = summary(job, "Project");
  assert.equal(statusLabel({ ...value, saved: false, execution: "interrupted", publication: "ready" }), "Выполнение прервано");
  assert.equal(statusLabel({ ...value, saved: false, execution: "failed", publication: "waiting_for_sync" }), "Не удалось завершить");
});
