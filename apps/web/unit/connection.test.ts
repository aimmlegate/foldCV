import assert from "node:assert/strict";
import test from "node:test";
import { ConnectionWorkflow, validConnection } from "../src/connection/workflow";

const ready = { state: "connected", version: "codex-cli 0.162.0-alpha.2", plan: "plus",
  models: ["gpt-6-luna"], selectedModel: null,
  quota: { state: "available", usedPercent: 25, resetsAt: 1800000000 }, metadataReady: true,
  generationReady: false, experimentalMode: false };

function response(body: object): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

test("connection response rejects arbitrary models, quotas and production readiness", () => {
  assert.equal(validConnection(ready), true);
  assert.equal(validConnection({ ...ready, generationReady: true }), false);
  assert.equal(validConnection({ ...ready, experimentalMode: true, selectedModel: "gpt-6-luna",
    generationReady: true }), true);
  assert.equal(validConnection({ ...ready, models: ["evil command --flag"] }), false);
  assert.equal(validConnection({ ...ready, selectedModel: "other" }), false);
  assert.equal(validConnection({ ...ready, quota: { ...ready.quota, usedPercent: Infinity } }), false);
  assert.equal(validConnection({ ...ready, state: "launcher_unsupported", models: [],
    selectedModel: null, metadataReady: false }), true);
});

test("detach discards a late metadata result", async () => {
  const deferred: { resolve?: (value: Response) => void } = {};
  const calls: string[] = [];
  const request: typeof fetch = (input) => {
    const path = String(input);
    calls.push(path);
    if (path.endsWith("/status")) return new Promise<Response>((resolve) => { deferred.resolve = resolve; });
    return Promise.resolve(response({ ...ready, state: "detached", version: null, plan: null, models: [],
      quota: { state: "unknown", usedPercent: null, resetsAt: null }, metadataReady: false }));
  };
  const workflow = new ConnectionWorkflow(() => {}, request);
  const pending = workflow.refresh();
  await workflow.detach();
  const finish = deferred.resolve;
  if (finish === undefined) throw new Error("status request was not started");
  finish(response(ready));
  await pending;
  assert.equal(workflow.view.snapshot.state, "detached");
  assert.deepEqual(calls, ["/v1/host/status", "/v1/host/detach"]);
});

test("cleanup block from detach survives a late stale status response", async () => {
  const deferred: { resolve?: (value: Response) => void } = {};
  const detachReply: { resolve?: (value: Response) => void } = {};
  let detachCalls = 0;
  const closed = { ...ready, state: "detached", version: null, plan: null, models: [], selectedModel: null,
    quota: { state: "unknown", usedPercent: null, resetsAt: null }, metadataReady: false };
  const request: typeof fetch = (input) => {
    if (String(input).endsWith("/status")) return new Promise<Response>((resolve) => { deferred.resolve = resolve; });
    detachCalls += 1;
    return new Promise<Response>((resolve) => { detachReply.resolve = resolve; });
  };
  const workflow = new ConnectionWorkflow(() => {}, request);
  const pending = workflow.refresh();
  const detaching = workflow.detach();
  await workflow.detach();
  assert.equal(workflow.view.detaching, true);
  assert.equal(detachCalls, 1);
  const confirm = detachReply.resolve;
  if (confirm === undefined) throw new Error("detach request was not started");
  confirm(response({ ...closed, state: "cleanup_blocked" }));
  await detaching;
  assert.equal(workflow.view.snapshot.state, "cleanup_blocked");
  assert.equal(workflow.view.detaching, false);
  const finish = deferred.resolve;
  if (finish === undefined) throw new Error("status request was not started");
  finish(response(closed));
  await pending;
  assert.equal(workflow.view.snapshot.state, "cleanup_blocked");
  assert.equal(workflow.view.error, null);
});
