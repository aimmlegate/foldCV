import assert from "node:assert/strict";
import test from "node:test";
import type { AssistantView } from "../src/assistant/controller";
import type { AgentEvent } from "../src/contracts/generated/agent_event";
import { activityItems, currentActivity } from "../src/workbench/assistant/activity";
import { validateContract } from "../src/contracts/validate";
import { running } from "./support/background-jobs";

const run = { id: "run", conversationId: "conversation", projectId: "project", clientRequestId: "request", state: "running" as const,
  model: "assistant", scope: { kind: "resume" as const }, allowEdits: true, allowWeb: false, createdAt: "2026-10-18T12:00:00Z",
  finishedAt: null, connectionEpoch: "account", deadline: "2026-10-18T12:05:00Z", ownerEpoch: 1, settingsRevision: 1,
  error: null, savedBatchId: null, outcomeUnknown: false, usage: null };
const view: AssistantView = { settings: null, capabilities: null, flags: { allowEdits: true, allowWeb: false }, conversations: [],
  conversationCursor: null, conversationId: "conversation", messages: [], messageCursor: null, sources: [], findings: [],
  run, receipts: [], activity: [], partial: "", partialTruncated: false, draft: "", submitting: false, pendingSend: false, error: null };
const base = (sequence: number) => ({ schemaVersion: 1 as const, id: `event_${sequence}`, runId: "run", projectId: "project",
  conversationId: "conversation", sequence, timestamp: `2026-10-18T12:00:${String(sequence).padStart(2, "0")}Z` });
const started: AgentEvent = { ...base(1), type: "tool.started", payload: { callId: "read", name: "get_original_source", error: null } };
const summary: AgentEvent = { ...base(2), type: "activity.updated", payload: { itemId: "summary", kind: "summary", text: "Сверяю факты с исходником." } };

test("public activity groups each tool and summary update without leaving a finished tool running", () => {
  const activity: AgentEvent[] = [started, summary, { ...summary, ...base(3), payload: { ...summary.payload, text: "Проверяю подтверждённые даты." } }];
  assert.equal(currentActivity({ ...view, activity }, true), "Читает исходник");
  assert.equal(currentActivity({ ...view, activity, partial: "Проверю исходник." }, true), "Читает исходник");
  const completed: AgentEvent = { ...started, ...base(4), type: "tool.completed" };
  activity.push(completed);
  const items = activityItems({ ...view, activity });
  assert.equal(items.length, 2);
  assert.equal(items.find(item => item.id === "summary")?.text, "Проверяю подтверждённые даты.");
  assert.equal(items.find(item => item.id === "read")?.state, "success");
  assert.equal(currentActivity({ ...view, activity }, true), "Модель готовит ответ");
});

test("queue, cancellation, uncertain send and editor publication take precedence over an old tool", () => {
  const current = { ...view, activity: [started, summary] };
  assert.equal(currentActivity({ ...current, run: { ...run, state: "queued" } }, true), "Ожидает очереди");
  assert.equal(currentActivity({ ...current, run: { ...run, state: "cancelling" } }, true), "Останавливаем…");
  assert.match(currentActivity({ ...current, pendingSend: true }, true), /Ответ на отправку потерян/);
  assert.equal(currentActivity({ ...current, run: { ...run, state: "completed" } }, true), "Подтверждаем изменения в редакторе");
  assert.equal(currentActivity({ ...current, loading: "Открываем диалог" }, false), "Открываем диалог");
});

test("activity is scoped to the current run and never renders unknown tool identifiers", () => {
  assert.deepEqual(activityItems({ ...view, activity: [{ ...summary, runId: "other" }] }), []);
  const item: AgentEvent = { ...started, payload: { ...started.payload, name: "PRIVATE_INTERNAL_COMMAND" } };
  assert.equal(currentActivity({ ...view, activity: [item] }, true), "Работает с резюме");
  assert.ok(!JSON.stringify(activityItems({ ...view, activity: [item] })).includes("PRIVATE_INTERNAL_COMMAND"));
});

test("background progress must belong to its job and keep sequence order", () => {
  const job = running("run");
  const event = { ...summary, projectId: job.submission.identity.projectId };
  assert.equal(validateContract("background_snapshot_v1", { ...job, activity: [event] }), true);
  assert.equal(validateContract("background_snapshot_v1", { ...job, activity: [{ ...event, runId: "foreign" }] }), false);
  assert.equal(validateContract("background_snapshot_v1", { ...job, activity: [{ ...event, projectId: "foreign" }] }), false);
  assert.equal(validateContract("background_snapshot_v1", { ...job, activity: [event, event] }), false);
});
