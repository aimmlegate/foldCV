import assert from "node:assert/strict";
import test from "node:test";
import type { AssistantView } from "../src/assistant/controller";
import type { AgentRun } from "../src/contracts/generated/agent_run";
import { activityText } from "../src/workbench/assistant/status";

const run: AgentRun = { id: "run", conversationId: "conversation", projectId: "project", clientRequestId: "request", state: "completed",
  model: "assistant", scope: { kind: "resume" }, allowEdits: true, allowWeb: false, createdAt: "2026-10-16T00:00:00Z",
  finishedAt: "2026-10-16T00:00:01Z", connectionEpoch: "account", deadline: "2026-10-16T00:05:00Z", ownerEpoch: 1,
  settingsRevision: 1, error: null, savedBatchId: null, outcomeUnknown: false, usage: null };
const view: AssistantView = { settings: null, capabilities: null, flags: { allowEdits: true, allowWeb: false }, conversations: [],
  conversationCursor: null, conversationId: "conversation", messages: [], messageCursor: null, sources: [], findings: [],
  run, receipts: [], activity: [], partial: "", partialTruncated: false, draft: "", submitting: false, pendingSend: false, error: null };

test("a terminal server run still waits for the mounted editor acknowledgment", () => {
  assert.equal(activityText(view, true), "Подтверждаем изменения в редакторе");
  assert.equal(activityText(view, false), "Завершено");
  assert.equal(activityText({ ...view, run: { ...run, state: "cancelled" } }, false), "Остановлено");
});
test("a new submission and a lost submission response keep their own states", () => {
  assert.equal(activityText({ ...view, submitting: true }, true), "Отправляем задачу…");
  assert.match(activityText({ ...view, pendingSend: true }, true), /Ответ на отправку потерян/);
});
