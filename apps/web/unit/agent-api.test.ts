import assert from "node:assert/strict";
import test from "node:test";
import type { AgentEvent } from "../src/contracts/generated/agent_event";
import { AgentBrowserApi } from "../src/assistant/api";
import { proposal } from "./support/assistant-proposal";

const owner = { token: "synthetic_owner_capability_0123456789", epoch: 1 };
const event: AgentEvent = { schemaVersion: 1, id: "event_1", sequence: 1, projectId: "project_1", conversationId: "conversation_1",
  runId: "run_1", timestamp: "2026-10-15T12:00:00Z", type: "message.delta", payload: { text: "Привет 😀" } };
test("assistant API streams fragmented UTF-8 with secrets only in the authenticated JSON body", async () => {
  let called = false;
  const transport: typeof fetch = (input, options) => {
    called = true; assert.equal(String(input).includes(owner.token), false); assert.equal(String(input).includes("?"), false);
    assert.equal(options?.credentials, "same-origin"); assert.equal(options?.cache, "no-store");
    const body: unknown = JSON.parse(typeof options?.body === "string" ? options.body : "null");
    assert.deepEqual(body, { owner, afterSequence: 0 });
    const raw = new TextEncoder().encode(JSON.stringify(event) + "\n\n");
    return Promise.resolve(new Response(new ReadableStream<Uint8Array>({ start(controller) {
      for (const byte of raw) controller.enqueue(new Uint8Array([byte])); controller.close();
    } }), { headers: { "Content-Type": "application/x-ndjson" } }));
  };
  const api = new AgentBrowserApi("project_1", transport), received: AgentEvent[] = [];
  for await (const item of api.events("run_1", owner, 0, new AbortController().signal)) received.push(item);
  assert.ok(called); assert.deepEqual(received, [event]);
});

test("assistant API rejects malformed or oversized event frames without exposing raw content", async () => {
  for (const raw of ["{bad}\n", JSON.stringify({ ...event, type: "unknown_state_change" }) + "\n", "x".repeat(65537)]) {
    const transport: typeof fetch = () => Promise.resolve(new Response(raw, { headers: { "Content-Type": "application/x-ndjson" } }));
    const api = new AgentBrowserApi("project_1", transport);
    await assert.rejects(async () => { for await (const _event of api.events("run_1", owner, 0, new AbortController().signal)) { /* Consume validated events only. */ } });
  }
});

test("lost UI claim reply resumes the same nonce over the versioned local API without generation", async () => {
  const value = proposal(), accepted = { protocolVersion: 1 as const, proposalId: value.id, version: value.version,
    contentSha256: value.contentSha256, acceptanceId: "click_1", owner }, requests: { path: string; body: unknown }[] = [];
  const transport: typeof fetch = (input, options) => {
    const path = String(input);
    assert.equal(options?.credentials, "same-origin");
    assert.equal(new Headers(options?.headers).get("X-FoldCV-Assistant-Protocol"), "1");
    const body: unknown = JSON.parse(typeof options?.body === "string" ? options.body : "null");
    requests.push({ path, body });
    if (path.endsWith("/claim")) return Promise.reject(new Error("Lost local reply"));
    assert.ok(path.endsWith("/resume"));
    return Promise.resolve(new Response(JSON.stringify({ schemaVersion: 1, protocolVersion: 1,
      proposal: value, result: null, claim: null })));
  };
  const api = new AgentBrowserApi(value.projectId, transport).reviewed(accepted);
  assert.ok(api.resolve);
  await assert.rejects(api.resolve("review_1"), /AGENT_SAVE_FAILED/);
  assert.equal(requests.length, 2);
  assert.deepEqual(requests.map(item => item.body), [accepted, accepted]);
  assert.ok(requests.every(item => item.path.includes("/applications/") && !item.path.includes(owner.token)));
});
