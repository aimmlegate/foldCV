import assert from "node:assert/strict";
import test from "node:test";
import type { AssistantView } from "../src/assistant/controller";
import { activityText } from "../src/workbench/assistant/status";
import { run as assistantRun, view as assistantView } from "./support/assistant";

const run = assistantRun("completed", "run", "conversation");
const view: AssistantView = assistantView({ run });

test("a terminal server run still waits for the mounted editor acknowledgment", () => {
  assert.equal(activityText(view, true), "Применяем правки");
  assert.equal(activityText(view, false), "Завершено");
  assert.equal(activityText({ ...view, run: { ...run, state: "cancelled" } }, false), "Остановлено");
});
test("Discard after a run has its own status", () => {
  assert.equal(activityText({ ...view, proposalBusy: "proposal-1", proposalAction: "discard" }, true), "Отклоняем правки");
  assert.equal(activityText({ ...view, proposalBusy: "proposal-1", proposalAction: "apply" }, true), "Применяем правки");
});
test("a new submission and a lost submission response keep their own states", () => {
  assert.equal(activityText({ ...view, submitting: true }, true), "Отправляем…");
  assert.match(activityText({ ...view, pendingSend: true }, true), /Нет ответа на отправку/);
});
