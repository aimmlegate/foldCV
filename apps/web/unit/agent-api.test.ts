import assert from "node:assert/strict";
import test from "node:test";
import { AgentApiFailure, AssistantApi, assistantSettings } from "../src/assistant/api";
import type { Fetcher } from "../src/rich/v7-connection";
import { run } from "./support/assistant";

function recording(reply: (path: string, init: RequestInit) => Response) {
  const requests: { path: string; method: string; body: string | null }[] = [];
  const fetcher: Fetcher = (path, init) => {
    requests.push({ path, method: init.method ?? "GET", body: typeof init.body === "string" ? init.body : null });
    return Promise.resolve(reply(path, init));
  };
  return { requests, fetcher };
}
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });

test("assistant routes are /v2 paths without query strings, and every POST carries a JSON body", async () => {
  const { requests, fetcher } = recording(path => json(path.includes("/events/") ? { run: run(), events: [], next: 7 } : run()));
  const api = new AssistantApi("template project", fetcher);
  await api.capabilities(); await api.createConversation(); await api.events("run-1", 7); await api.cancel("run-1");
  await api.submit("conversation-1", { clientRequestId: "request-1", message: "Проверь", allowEdits: false, allowWeb: true, selection: null });
  await api.discard("proposal-1"); await api.proposals(); await assistantSettings(fetcher);
  assert.deepEqual(requests.map(item => `${item.method} ${item.path}`), [
    "GET /v2/projects/template%20project/assistant/capabilities", "POST /v2/projects/template%20project/assistant/conversations",
    "GET /v2/projects/template%20project/assistant/runs/run-1/events/7", "POST /v2/projects/template%20project/assistant/runs/run-1/cancel",
    "POST /v2/projects/template%20project/assistant/conversations/conversation-1/runs",
    "POST /v2/projects/template%20project/assistant/proposals/proposal-1/discard", "GET /v2/projects/template%20project/assistant/proposals",
    "GET /v1/settings/assistant"]);
  assert.ok(requests.every(item => !item.path.includes("?")));
  assert.ok(requests.filter(item => item.method === "POST").every(item => item.body !== null));
  assert.deepEqual(JSON.parse(requests[4]?.body ?? "null"), { clientRequestId: "request-1", message: "Проверь", allowEdits: false, allowWeb: true, selection: null });
  assert.equal(requests.find(item => item.path.endsWith("/discard"))?.body, "{}");
});

test("server refusals keep their code, status and body; a broken reply is INVALID_RESULT", async () => {
  const stale = new AssistantApi("p", recording(() => json({ error: { code: "ASSISTANT_RUN_ACTIVE", retryable: false } }, 409)).fetcher);
  await assert.rejects(stale.submit("c", { clientRequestId: "r", message: "m", allowEdits: true, allowWeb: false }),
    (error: unknown) => error instanceof AgentApiFailure && error.code === "ASSISTANT_RUN_ACTIVE" && error.status === 409);
  const broken = new AssistantApi("p", recording(() => new Response("<html>", { status: 200 })).fetcher);
  await assert.rejects(broken.capabilities(), (error: unknown) => error instanceof AgentApiFailure && error.code === "INVALID_RESULT");
});
