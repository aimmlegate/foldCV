import assert from "node:assert/strict";
import test from "node:test";
import { ConnectionWorkflow, connectionSummary, modelGroups, validConnection, type ConnectionSnapshot } from "../src/connection/workflow";
import { errorMessage } from "../src/errors/messages";

type Entry = Record<string, unknown> & { kind: string; enabled: boolean; metadataReady: boolean; models: string[] };
const codex: Entry = { kind: "codex_cli", display: "Codex", subscription: "ChatGPT", publisher: "OpenAI", loginCode: false, installed: true,
  enabled: true, state: "connected", version: "codex-cli 0.162.0-alpha.2", versionStatus: "supported", plan: "plus", models: ["gpt-6-luna"],
  quota: { state: "available", usedPercent: 25, resetsAt: 1800000000 }, metadataReady: true, installation: null };
const claude: Entry = { kind: "claude_cli", display: "Claude", subscription: "Claude", publisher: "Anthropic", loginCode: true, installed: true,
  enabled: true, state: "connected", version: "2.1.308 (Claude Code)", versionStatus: "supported", plan: "max", models: ["claude-sonnet-5-5"],
  quota: { state: "not_provided", usedPercent: null, resetsAt: null }, metadataReady: true, installation: null };
const off = { state: "unchecked", version: null, versionStatus: null, plan: null, models: [], metadataReady: false,
  quota: { state: "unknown", usedPercent: null, resetsAt: null } };

/** A reply as the service builds it: the named provider at the top level, the catalog of the providers that are on. */
function reply(providers: Entry[], named = "codex_cli", extra: Record<string, unknown> = {}) {
  const top = providers.find(item => item.kind === named) ?? codex;
  const models = providers.filter(item => item.enabled && item.metadataReady).flatMap(item => item.models);
  return { provider: named, providers, state: top.state, version: top.version, versionStatus: top.versionStatus, plan: top.plan,
    quota: top.quota, installation: top.installation, models, selectedModel: null, metadataReady: models.length > 0,
    generationReady: false, experimentalMode: false, ...extra };
}

function response(body: object): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

const refusal = (code: string, status: number) => new Response(JSON.stringify({ error: { code, retryable: false, stage: "host" } }),
  { status, headers: { "Content-Type": "application/json" } });
const ready = reply([codex]);

test("connection response rejects arbitrary models, quotas and production readiness", () => {
  assert.equal(validConnection(ready), true);
  assert.equal(validConnection({ ...ready, generationReady: true }), false);
  assert.equal(validConnection({ ...ready, experimentalMode: true, selectedModel: "gpt-6-luna", generationReady: true }), true);
  assert.equal(validConnection({ ...ready, models: ["evil command --flag"] }), false);
  assert.equal(validConnection({ ...ready, selectedModel: "other" }), false);
  assert.equal(validConnection({ ...ready, quota: { ...(ready.quota as object), usedPercent: Infinity } }), false);
  // A catalog model must belong to a provider that is on.
  assert.equal(validConnection({ ...ready, models: ["gpt-6-luna", "claude-sonnet-5-5"] }), false);
  assert.equal(validConnection(reply([{ ...codex, ...off, state: "launcher_unsupported" }])), true);
});

test("every provider entry is checked: kind, names, switch, state and its own catalog", () => {
  assert.equal(validConnection(reply([codex, claude], "claude_cli")), true);
  assert.equal(validConnection(reply([codex], "claude_cli")), false);
  assert.equal(validConnection(reply([{ ...codex, kind: "grok_cli" }], "grok_cli")), false);
  assert.equal(validConnection(reply([codex, codex])), false);
  for (const broken of [{ display: "" }, { installed: "yes" }, { enabled: "on" }, { state: "ready" }, { versionStatus: "broken" },
    { models: ["a b"] }, { quota: { state: "plenty", usedPercent: null, resetsAt: null } }]) {
    assert.equal(validConnection({ ...ready, providers: [{ ...codex, ...broken }] }), false, JSON.stringify(broken));
  }
  const { enabled: _enabled, ...unswitched } = codex;
  assert.equal(validConnection({ ...ready, providers: [unswitched] }), false);
  const { provider: _provider, ...unnamed } = ready;
  assert.equal(validConnection(unnamed), false);
});

test("models are grouped by the provider that runs them and the sidebar names the connected ones", () => {
  const both = reply([codex, claude]) as ConnectionSnapshot;
  assert.deepEqual(modelGroups(both), [{ label: "Codex", models: ["gpt-6-luna"] }, { label: "Claude", models: ["claude-sonnet-5-5"] }]);
  assert.deepEqual(modelGroups(reply([codex, { ...claude, enabled: false }]) as ConnectionSnapshot), [{ label: "Codex", models: ["gpt-6-luna"] }]);
  assert.equal(connectionSummary(both), "Codex и Claude · подписка");
  assert.equal(connectionSummary(reply([{ ...codex, ...off }, { ...claude, enabled: false, ...off }]) as ConnectionSnapshot), "Подключение не проверено");
  assert.equal(connectionSummary(reply([{ ...codex, ...off, state: "detached" }]) as ConnectionSnapshot), "Модель отключена");
  assert.equal(connectionSummary(null), "Подключение не проверено");
});

test("host requests name their provider; turning one on checks it and a model is saved through its provider", async () => {
  const calls: { path: string; body: unknown }[] = [];
  const request: typeof fetch = (input, init) => {
    const path = String(input), body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : null;
    calls.push({ path, body });
    if (path.endsWith("/enable")) return Promise.resolve(response(reply([codex, { ...claude, ...off }], "claude_cli")));
    if (path.endsWith("/connection")) return Promise.resolve(response(reply([codex, { ...claude, ...off, enabled: false }])));
    return Promise.resolve(response(reply([codex, claude], String(body?.provider ?? "codex_cli"),
      path.endsWith("/select") ? { selectedModel: "claude-sonnet-5-5" } : {})));
  };
  const workflow = new ConnectionWorkflow(() => {}, request);
  await workflow.peek();
  await workflow.enable("claude_cli", true);
  await workflow.select("claude-sonnet-5-5");
  await workflow.detach("codex_cli");
  assert.deepEqual(calls.map(call => [call.path, call.body]), [
    ["/v1/settings/connection", null],
    ["/v1/host/enable", { provider: "claude_cli", enabled: true }],
    ["/v1/host/status", { provider: "claude_cli" }],
    ["/v1/host/select", { provider: "claude_cli", model: "claude-sonnet-5-5" }],
    ["/v1/host/detach", { provider: "codex_cli" }],
  ]);
  assert.equal(workflow.view.snapshot.selectedModel, null, "the detach reply is the newest");
});

test("opening settings checks only the providers that are on and not checked yet", async () => {
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, (input, init) => {
    calls.push(String(input) + (init?.body ? " " + String(init.body) : ""));
    return Promise.resolve(response(String(input).endsWith("/connection")
      ? reply([{ ...codex, ...off }, { ...claude, ...off, enabled: false }]) : reply([codex, { ...claude, ...off, enabled: false }])));
  });
  await workflow.peek();
  assert.deepEqual(calls, ["/v1/settings/connection", '/v1/host/status {"provider":"codex_cli"}']);
  await workflow.peek(false);
  assert.equal(calls.length, 3);
});

test("one provider's check runs while the other one is busy, and each keeps its own activity", async () => {
  const deferred: { resolve?: (value: Response) => void } = {};
  const workflow = new ConnectionWorkflow(() => {}, (input, init) => {
    const body = JSON.parse(String(init?.body ?? "{}")) as { provider?: string };
    if (body.provider === "claude_cli") return new Promise<Response>(resolve => { deferred.resolve = resolve; });
    return Promise.resolve(response(reply([codex, { ...claude, ...off }])));
  });
  const slow = workflow.refresh("claude_cli");
  await workflow.refresh("codex_cli");
  assert.equal(workflow.view.activity.claude_cli?.pending, true);
  assert.equal(workflow.view.activity.codex_cli, undefined);
  assert.equal(workflow.view.pending, true);
  deferred.resolve?.(response(reply([codex, claude], "claude_cli")));
  await slow;
  assert.equal(workflow.view.pending, false);
  assert.deepEqual(workflow.view.snapshot.models, ["gpt-6-luna", "claude-sonnet-5-5"]);
});

test("a sign-in code is sent only while that provider signs in and only in the code format", async () => {
  const calls: { path: string; body: unknown }[] = [];
  const pending = reply([codex, { ...claude, ...off, state: "login_pending" }], "claude_cli");
  const request: typeof fetch = (input, init) => {
    calls.push({ path: String(input), body: init?.body ? JSON.parse(String(init.body)) : null });
    return Promise.resolve(response(pending));
  };
  const workflow = new ConnectionWorkflow(() => {}, request);
  try {
    assert.equal(await workflow.sendLoginCode("claude_cli", "abc"), false, "nothing is pending before the first reply");
    await workflow.peek(false);
    assert.equal(await workflow.sendLoginCode("codex_cli", "abc"), false);
    assert.equal(await workflow.sendLoginCode("claude_cli", "two words"), false);
    assert.equal(await workflow.sendLoginCode("claude_cli", "  code-1#state  "), true);
    assert.deepEqual(calls.at(-1), { path: "/v1/host/login-code", body: { provider: "claude_cli", code: "code-1#state" } });
    assert.equal(calls.filter(call => call.path.endsWith("/login-code")).length, 1);
  } finally { workflow.close(); }
});

const signedOut = (state = "login_required") => reply([{ ...codex, ...off, state }], "codex_cli", { experimentalMode: true });

test("a refused sign-in returns the card to its button and keeps the service's code", async () => {
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    return Promise.resolve(path.endsWith("/login") ? refusal("BUSY", 429) : response(signedOut()));
  });
  await workflow.peek(false);
  await workflow.login("codex_cli");
  assert.equal(workflow.entry("codex_cli")?.state, "login_required");
  assert.equal(workflow.view.activity.codex_cli?.error, "BUSY");
  assert.equal(errorMessage(workflow.view.activity.codex_cli?.error), errorMessage("BUSY"));
  assert.match(errorMessage(workflow.view.activity.codex_cli?.error), /другое действие/u);
  assert.deepEqual(calls, ["/v1/settings/connection", "/v1/host/login", "/v1/settings/connection"]);
});

test("a sign-in whose reply was lost shows as running again after the read", async () => {
  let reads = 0;
  const workflow = new ConnectionWorkflow(() => {}, input => {
    if (String(input).endsWith("/login")) return Promise.reject(new TypeError("fetch failed"));
    return Promise.resolve(response(signedOut(++reads > 1 ? "login_pending" : "login_required")));
  });
  try {
    await workflow.peek(false);
    await workflow.login("codex_cli");
    assert.equal(workflow.entry("codex_cli")?.state, "login_pending");
  } finally { workflow.close(); }
});

test("a sign-in found by a read is followed until it ends", async () => {
  let reads = 0, finished: (() => void) | undefined;
  const ended = new Promise<void>(resolve => { finished = resolve; });
  const workflow = new ConnectionWorkflow(view => { if (view.snapshot.providers[0]?.state === "connected") finished?.(); }, () => {
    reads += 1;
    return Promise.resolve(response(reads < 3 ? signedOut("login_pending") : reply([codex])));
  }, 1);
  try {
    await workflow.peek(false);
    assert.equal(workflow.entry("codex_cli")?.state, "login_pending");
    await ended;
    const seen = reads;
    await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(reads, seen, "the reads stop with the sign-in");
  } finally { workflow.close(); }
});

test("a failed read of the state is reported and can be repeated", async () => {
  for (const failure of [() => Promise.reject(new TypeError("fetch failed")), () => Promise.resolve(response({ ...ready, plan: "team-premium" }))]) {
    let down = true;
    const views: boolean[] = [];
    const workflow = new ConnectionWorkflow(view => views.push(view.readFailed), () => down ? failure() : Promise.resolve(response(ready)));
    await workflow.peek();
    assert.equal(workflow.view.readFailed, true);
    assert.equal(workflow.view.snapshot.provider, null);
    down = false;
    await workflow.peek();
    assert.equal(workflow.view.readFailed, false);
    assert.equal(workflow.view.snapshot.provider, "codex_cli");
    assert.equal(views.at(-1), false);
  }
});

test("refusals of every host request keep their code; a lost reply keeps the client's text", async () => {
  const replies: Record<string, Response> = {};
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input), refused = replies[path];
    return refused ? Promise.resolve(refused) : Promise.resolve(response(reply([{ ...codex, ...off, state: "cli_missing", installation }], "codex_cli", { experimentalMode: true })));
  });
  await workflow.peek(false);
  replies["/v1/host/install"] = refusal("INSTALL_NOT_AVAILABLE", 409);
  await workflow.install("codex_cli");
  assert.equal(workflow.view.activity.codex_cli?.error, "INSTALL_NOT_AVAILABLE");
  replies["/v1/host/enable"] = refusal("PROVIDER_INACTIVE", 409);
  await workflow.enable("codex_cli", false);
  assert.equal(workflow.view.activity.codex_cli?.error, "PROVIDER_INACTIVE");
  replies["/v1/host/detach"] = refusal("BUSY", 429);
  await workflow.detach("codex_cli");
  assert.equal(workflow.view.activity.codex_cli?.error, "BUSY");
  replies["/v1/host/status"] = new Response("<html>", { status: 502 });
  await workflow.refresh("codex_cli");
  assert.equal(workflow.view.activity.codex_cli?.error, "REQUEST_FAILED");
  workflow.close();
});

test("saving a processing model reports its own provider only, not another one's old error", async () => {
  const workflow = new ConnectionWorkflow(() => {}, (input, init) => {
    const path = String(input), body = init?.body ? JSON.parse(String(init.body)) as { provider?: string } : {};
    if (path.endsWith("/status") && body.provider === "claude_cli") return Promise.resolve(refusal("BUSY", 429));
    if (path.endsWith("/select")) return Promise.resolve(body.provider === "codex_cli"
      ? response(reply([codex, claude], "codex_cli", { selectedModel: "gpt-6-luna" })) : refusal("MODEL_DENIED", 409));
    return Promise.resolve(response(reply([codex, claude])));
  });
  await workflow.peek(false);
  await workflow.refresh("claude_cli");
  assert.equal(workflow.view.error, "BUSY");
  assert.equal(await workflow.select("gpt-6-luna"), true);
  assert.equal(await workflow.select("claude-sonnet-5-5"), false);
  assert.equal(await workflow.select("unknown-model"), false);
});

test("detach discards a late metadata result of the same provider", async () => {
  const deferred: { resolve?: (value: Response) => void } = {};
  const calls: string[] = [];
  const detached = reply([{ ...codex, ...off, state: "detached" }]);
  const request: typeof fetch = (input) => {
    const path = String(input);
    calls.push(path);
    if (path.endsWith("/status")) return new Promise<Response>((resolve) => { deferred.resolve = resolve; });
    return Promise.resolve(response(detached));
  };
  const workflow = new ConnectionWorkflow(() => {}, request);
  const pending = workflow.refresh("codex_cli");
  await workflow.detach("codex_cli");
  deferred.resolve?.(response(ready));
  await pending;
  assert.equal(workflow.view.snapshot.providers[0]?.state, "detached");
  assert.deepEqual(calls, ["/v1/host/status", "/v1/host/detach"]);
});

test("cleanup block from detach survives a late stale status response", async () => {
  const deferred: { resolve?: (value: Response) => void } = {};
  const detachReply: { resolve?: (value: Response) => void } = {};
  let detachCalls = 0;
  const closed = reply([{ ...codex, ...off, state: "detached" }]);
  const request: typeof fetch = (input) => {
    if (String(input).endsWith("/status")) return new Promise<Response>((resolve) => { deferred.resolve = resolve; });
    detachCalls += 1;
    return new Promise<Response>((resolve) => { detachReply.resolve = resolve; });
  };
  const workflow = new ConnectionWorkflow(() => {}, request);
  const pending = workflow.refresh("codex_cli");
  const detaching = workflow.detach("codex_cli");
  await workflow.detach("codex_cli");
  assert.equal(workflow.view.detaching, true);
  assert.equal(detachCalls, 1);
  detachReply.resolve?.(response(reply([{ ...codex, ...off, state: "cleanup_blocked" }])));
  await detaching;
  assert.equal(workflow.view.snapshot.providers[0]?.state, "cleanup_blocked");
  assert.equal(workflow.view.detaching, false);
  deferred.resolve?.(response(closed));
  await pending;
  assert.equal(workflow.view.snapshot.providers[0]?.state, "cleanup_blocked");
  assert.equal(workflow.view.error, null);
});

const installation = { state: "idle", available: true, version: "0.162.0-alpha.17.2", downloadedBytes: 0,
  totalBytes: 132097637, error: null };
const missingCodex: Entry = { ...codex, ...off, state: "cli_missing", installation };
const missing = reply([missingCodex], "codex_cli", { experimentalMode: true });
const withCodex = (change: Record<string, unknown>) => reply([{ ...missingCodex, ...change }], "codex_cli", { experimentalMode: true });

test("installation validates bounded progress and rejects unsafe server values", () => {
  assert.equal(validConnection(missing), true);
  for (const broken of [{ downloadedBytes: -1 }, { downloadedBytes: installation.totalBytes + 1 },
    { totalBytes: 0 }, { downloadedBytes: Infinity }, { available: "yes" }, { version: "../../cli" }, { error: "<html>" }, { error: "unknown_error" }]) {
    assert.equal(validConnection(withCodex({ installation: { ...installation, ...broken } })), false);
  }
});

test("successful installation refreshes native login without restarting", async () => {
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    if (path.endsWith("/install")) return Promise.resolve(response(withCodex({ state: "unchecked", installation: { ...installation, state: "ready" } })));
    return Promise.resolve(response(path.endsWith("/status") && calls.length > 2
      ? withCodex({ state: "login_required", installation: { ...installation, state: "ready" } }) : missing));
  });
  await workflow.refresh("codex_cli");
  await workflow.install("codex_cli");
  assert.deepEqual(calls, ["/v1/host/status", "/v1/host/install", "/v1/host/status"]);
  assert.equal(workflow.entry("codex_cli")?.state, "login_required");
  assert.equal(workflow.view.pending, false);
});

test("installation failure offers retry without starting sign-in or metadata", async () => {
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    return Promise.resolve(response(path.endsWith("/install") ? withCodex({ installation: { ...installation, state: "failed", error: "checksum_failed" } }) : missing));
  });
  await workflow.refresh("codex_cli");
  await workflow.install("codex_cli");
  await workflow.install("codex_cli");
  assert.deepEqual(calls, ["/v1/host/status", "/v1/host/install", "/v1/host/install"]);
  assert.equal(workflow.entry("codex_cli")?.installation?.error, "checksum_failed");
});

test("cancelled installation ignores its late success and skips automatic refresh", async () => {
  let finish: ((value: Response) => void) | undefined;
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    if (path.endsWith("/install")) return new Promise(resolve => { finish = resolve; });
    return Promise.resolve(response(path.endsWith("/cancel-install") ? withCodex({ installation: { ...installation, state: "cancelled", error: "cancelled" } }) : missing));
  });
  await workflow.refresh("codex_cli");
  const pending = workflow.install("codex_cli");
  await workflow.cancelInstall("codex_cli");
  finish?.(response(withCodex({ state: "unchecked", installation: { ...installation, state: "ready" } })));
  await pending;
  assert.equal(workflow.entry("codex_cli")?.installation?.state, "cancelled");
  assert.deepEqual(calls, ["/v1/host/status", "/v1/host/install", "/v1/host/cancel-install"]);
});

test("opening settings detects a missing CLI without downloading", async () => {
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    return Promise.resolve(response(path.endsWith("/connection") ? withCodex({ state: "unchecked" }) : missing));
  });
  await workflow.peek();
  assert.deepEqual(calls, ["/v1/settings/connection", "/v1/host/status"]);
  assert.equal(workflow.entry("codex_cli")?.state, "cli_missing");
});

test("cancelling after installation already committed still refreshes login", async () => {
  const calls: string[] = [];
  const workflow = new ConnectionWorkflow(() => {}, input => {
    const path = String(input);
    calls.push(path);
    return Promise.resolve(response(path.endsWith("/cancel-install") ? withCodex({ state: "unchecked", installation: { ...installation, state: "ready" } })
      : path.endsWith("/connection") ? missing : withCodex({ state: "login_required" })));
  });
  await workflow.peek(false);
  await workflow.cancelInstall("codex_cli");
  assert.deepEqual(calls, ["/v1/settings/connection", "/v1/host/cancel-install", "/v1/host/status"]);
  assert.equal(workflow.entry("codex_cli")?.state, "login_required");
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
      return Promise.resolve(response(withCodex({ state: "login_required", installation: { ...installation, state: "ready" } })));
    }
    peeks += 1;
    return Promise.resolve(response(withCodex({ state: peeks === 1 ? "cli_missing" : "unchecked",
      installation: { ...installation, state: peeks === 1 ? "downloading" : "ready" } })));
  });
  try {
    await workflow.peek();
    await Promise.race([completed, new Promise<never>((_resolve, reject) => { setTimeout(() => reject(new Error("Progress did not resume")), 1500); })]);
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(workflow.entry("codex_cli")?.state, "login_required");
    assert.deepEqual(calls, ["/v1/settings/connection", "/v1/settings/connection", "/v1/host/status"]);
  } finally { workflow.close(); }
});
