import assert from "node:assert/strict";
import test from "node:test";
import { ConnectionWorkflow, providerNames, validConnection, type ConnectionSnapshot } from "../src/connection/workflow";

const codex = { kind: "codex_cli", display: "Codex", subscription: "ChatGPT", publisher: "OpenAI", loginCode: false, installed: true };
const claude = { kind: "claude_cli", display: "Claude", subscription: "Claude", publisher: "Anthropic", loginCode: true, installed: true };
const ready = { provider: "codex_cli", providers: [codex], providerNotice: null, state: "connected",
  version: "codex-cli 0.162.0-alpha.2", versionStatus: "supported", plan: "plus",
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

test("connection response names a listed active provider and bounded provider fields", () => {
  assert.equal(validConnection({ ...ready, providers: [codex, claude], provider: "claude_cli", versionStatus: "graceful",
    quota: { state: "not_provided", usedPercent: null, resetsAt: null } }), true);
  assert.equal(validConnection({ ...ready, provider: "claude_cli" }), false);
  assert.equal(validConnection({ ...ready, provider: "grok_cli", providers: [{ ...codex, kind: "grok_cli" }] }), false);
  assert.equal(validConnection({ ...ready, providers: [codex, codex] }), false);
  assert.equal(validConnection({ ...ready, providers: [{ ...codex, display: "" }] }), false);
  assert.equal(validConnection({ ...ready, providers: [{ ...codex, installed: "yes" }] }), false);
  const { loginCode: _loginCode, ...noCode } = codex;
  assert.equal(validConnection({ ...ready, providers: [noCode] }), false);
  assert.equal(validConnection({ ...ready, providerNotice: "other" }), false);
  assert.equal(validConnection({ ...ready, versionStatus: "broken" }), false);
  const { provider: _provider, ...unnamed } = ready;
  assert.equal(validConnection(unnamed), false);
  assert.equal(providerNames({ ...ready, provider: "claude_cli", providers: [codex, claude] } as ConnectionSnapshot).display, "Claude");
});

test("host requests name the provider and a switch checks the new provider", async () => {
  const calls: { path: string; body: unknown }[] = [];
  const both = { ...ready, providers: [codex, claude] };
  const request: typeof fetch = (input, init) => {
    const path = String(input);
    calls.push({ path, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (path.endsWith("/select-provider")) return Promise.resolve(response({ ...both, provider: "claude_cli", state: "unchecked",
      version: null, versionStatus: null, plan: null, models: [], quota: { state: "unknown", usedPercent: null, resetsAt: null }, metadataReady: false }));
    if (path.endsWith("/status") && calls.length > 2) return Promise.resolve(response({ ...both, provider: "claude_cli", models: ["claude-sonnet-5-5"],
      quota: { state: "not_provided", usedPercent: null, resetsAt: null } }));
    return Promise.resolve(response(both));
  };
  const workflow = new ConnectionWorkflow(() => {}, request);
  await workflow.refresh();
  assert.equal(await workflow.selectProvider("codex_cli"), false);
  assert.equal(await workflow.selectProvider("claude_cli"), true);
  assert.deepEqual(calls.map(call => [call.path, call.body]), [
    ["/v1/host/status", {}],
    ["/v1/host/select-provider", { provider: "claude_cli" }],
    ["/v1/host/status", { provider: "claude_cli" }],
  ]);
  assert.equal(workflow.view.snapshot.provider, "claude_cli");
  assert.equal(workflow.view.snapshot.quota.state, "not_provided");
  await workflow.detach();
  assert.deepEqual(calls.at(-1), { path: "/v1/host/detach", body: { provider: "claude_cli" } });
});

test("a sign-in code is sent only while signing in and only in the code format", async () => {
  const calls: { path: string; body: unknown }[] = [];
  const pending = { ...ready, provider: "claude_cli", providers: [codex, claude], state: "login_pending" };
  const request: typeof fetch = (input, init) => {
    calls.push({ path: String(input), body: init?.body ? JSON.parse(String(init.body)) : null });
    return Promise.resolve(response(String(input).endsWith("/connection") ? pending : pending));
  };
  const workflow = new ConnectionWorkflow(() => {}, request);
  assert.equal(await workflow.sendLoginCode("abc"), false, "nothing is pending before the first reply");
  await workflow.peek();
  assert.equal(await workflow.sendLoginCode("two words"), false);
  assert.equal(await workflow.sendLoginCode("  code-1#state  "), true);
  assert.deepEqual(calls.at(-1), { path: "/v1/host/login-code", body: { provider: "claude_cli", code: "code-1#state" } });
  assert.equal(calls.filter(call => call.path.endsWith("/login-code")).length, 1);
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

const installation = { state: "idle", available: true, version: "0.162.0-alpha.17.2", downloadedBytes: 0,
  totalBytes: 132097637, error: null };
const missing = { ...ready, state: "cli_missing", models: [], metadataReady: false, experimentalMode: true, installation };

test("installation validates bounded progress and rejects unsafe server values", () => {
  assert.equal(validConnection(missing), true);
  for (const broken of [{ downloadedBytes: -1 }, { downloadedBytes: installation.totalBytes + 1 },
    { totalBytes: 0 }, { downloadedBytes: Infinity }, { available: "yes" }, { version: "../../cli" }, { error: "<html>" }, { error: "unknown_error" }]) {
    assert.equal(validConnection({ ...missing, installation: { ...installation, ...broken } }), false);
  }
});

test("successful installation refreshes native login without restarting", async () => {
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    if (path.endsWith("/install")) return Promise.resolve(response({ ...missing, state: "unchecked", installation: { ...installation, state: "ready" } }));
    return Promise.resolve(response(path.endsWith("/status") && calls.length > 2 ? { ...missing, state: "login_required", installation: { ...installation, state: "ready" } } : missing));
  });
  await workflow.refresh();
  await workflow.install();
  assert.deepEqual(calls, ["/v1/host/status", "/v1/host/install", "/v1/host/status"]);
  assert.equal(workflow.view.snapshot.state, "login_required");
  assert.equal(workflow.view.pending, false);
});

test("installation failure offers retry without starting sign-in or metadata", async () => {
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    return Promise.resolve(response(path.endsWith("/install") ? { ...missing, installation: { ...installation, state: "failed", error: "checksum_failed" } } : missing));
  });
  await workflow.refresh();
  await workflow.install();
  await workflow.install();
  assert.deepEqual(calls, ["/v1/host/status", "/v1/host/install", "/v1/host/install"]);
  assert.equal(workflow.view.snapshot.installation?.error, "checksum_failed");
});

test("cancelled installation ignores its late success and skips automatic refresh", async () => {
  let finish: ((value: Response) => void) | undefined;
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    if (path.endsWith("/install")) return new Promise(resolve => { finish = resolve; });
    return Promise.resolve(response(path.endsWith("/cancel-install") ? { ...missing, installation: { ...installation, state: "cancelled", error: "cancelled" } } : missing));
  });
  await workflow.refresh();
  const pending = workflow.install();
  await workflow.cancelInstall();
  if (!finish) throw new Error("Installation was not started");
  finish(response({ ...missing, state: "unchecked", installation: { ...installation, state: "ready" } }));
  await pending;
  assert.equal(workflow.view.snapshot.installation?.state, "cancelled");
  assert.deepEqual(calls, ["/v1/host/status", "/v1/host/install", "/v1/host/cancel-install"]);
});

test("opening settings detects a missing CLI without downloading", async () => {
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    return Promise.resolve(response(path.endsWith("/connection") ? { ...missing, state: "unchecked" } : missing));
  });
  await workflow.peek();
  assert.deepEqual(calls, ["/v1/settings/connection", "/v1/host/status"]);
  assert.equal(workflow.view.snapshot.state, "cli_missing");
});

test("cancelling after installation already committed still refreshes login", async () => {
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    return Promise.resolve(response(path.endsWith("/cancel-install") ? { ...missing, state: "unchecked", installation: { ...installation, state: "ready" } } : { ...missing, state: "login_required" }));
  });
  await workflow.cancelInstall();
  assert.deepEqual(calls, ["/v1/host/cancel-install", "/v1/host/status"]);
  assert.equal(workflow.view.snapshot.state, "login_required");
});

test("returning to settings resumes installation progress and refreshes completed setup", async () => {
  const calls: string[] = [];
  let peeks = 0;
  let connected: (() => void) | undefined;
  const completed = new Promise<void>(resolve => { connected = resolve; });
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    if (path.endsWith("/status")) {
      connected?.();
      return Promise.resolve(response({ ...missing, state: "login_required", installation: { ...installation, state: "ready" } }));
    }
    peeks += 1;
    return Promise.resolve(response({ ...missing, state: peeks === 1 ? "cli_missing" : "unchecked",
      installation: { ...installation, state: peeks === 1 ? "downloading" : "ready" } }));
  });
  try {
    await workflow.peek();
    await workflow.install();
    await Promise.race([completed, new Promise<never>((_resolve, reject) => { setTimeout(() => reject(new Error("Progress did not resume")), 1500); })]);
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(workflow.view.snapshot.state, "login_required");
    assert.deepEqual(calls, ["/v1/settings/connection", "/v1/settings/connection", "/v1/host/status"]);
  } finally { workflow.close(); }
});
