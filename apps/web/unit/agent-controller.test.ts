import assert from "node:assert/strict";
import test from "node:test";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import type { AgentRun } from "../src/contracts/generated/agent_run";
import type { AgentRunRequest } from "../src/contracts/generated/agent_run_request";
import type { AgentEvent } from "../src/contracts/generated/agent_event";
import type { AgentSettings } from "../src/contracts/generated/agent_settings";
import type { AgentCapabilities } from "../src/contracts/generated/agent_capabilities";
import type { AgentHistoryOffer } from "../src/contracts/generated/agent_history_offer";
import type { AgentClaimResult } from "../src/contracts/generated/agent_claim_result";
import type { AgentCommitResult } from "../src/contracts/generated/agent_commit_result";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import { AgentApiFailure } from "../src/assistant/api";
import { AssistantController, type AssistantApi } from "../src/assistant/controller";
import { deferred } from "./support/background-writer";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { taskCatalog } from "./support/assistant-capabilities";

const now = "2026-10-15T12:00:00Z";
const wait = () => new Promise<void>(resolve => { setImmediate(resolve); });

test("unsupported task preflight retains the draft and never captures or submits an action", async () => {
  const h = harness();
  let captured = false;
  h.api.tasks = () => Promise.resolve(taskCatalog());
  h.api.checkMessage = () => Promise.resolve({ schemaVersion: 1, protocolVersion: 1, projectId: "project_1",
    catalogRevision: "b".repeat(64), taskId: "export_pdf", needsPlanning: false,
    availability: { state: "unsupported", reasonCode: "ASSISTANT_UNSUPPORTED_TASK", reason: "PDF недоступен.", remedy: "Экспортируйте DOCX." } });
  try {
    await h.controller.init();
    h.controller.draft("Экспортируй PDF");
    await h.controller.send(() => { captured = true; return baseline(); });
    assert.equal(captured, false);
    assert.equal(h.requests.length, 0);
    assert.equal(h.controller.view.draft, "Экспортируй PDF");
    assert.equal(h.controller.view.taskReason, "PDF недоступен. Экспортируйте DOCX.");
    h.controller.draft("Проверь текст");
    assert.equal(h.controller.view.taskReason, null);
    assert.equal(h.controller.view.error, null);
  } finally { h.controller.close(); }
});

test("a delayed catalog reply cannot restore readiness after a newer invalidation", async () => {
  const h = harness(), older = deferred<ReturnType<typeof taskCatalog>>();
  let calls = 0;
  const newer = taskCatalog(); newer.catalogRevision = "c".repeat(64);
  h.api.tasks = () => ++calls === 1 ? older.promise : Promise.resolve(newer);
  try {
    const pending = h.controller.refreshCatalog();
    await h.controller.refreshCatalog();
    older.resolve(taskCatalog()); await pending;
    assert.equal(h.controller.view.taskCatalog?.catalogRevision, newer.catalogRevision);
  } finally { h.controller.close(); }
});

test("foreground send binds editor history to its owner before submission and skips it in read-only", async () => {
  for (const readOnly of [false, true]) {
    const h = harness(), offers: AgentHistoryOffer[] = [];
    h.api.access = () => Promise.resolve({ revision: 1, readOnly });
    h.api.offerHistory = value => {
      assert.equal(h.requests.length, 0);
      offers.push(value);
      return Promise.resolve({});
    };
    try {
      await h.controller.init();
      h.controller.draft("Read the whole project and its facts.");
      await h.controller.send(async () => ({ ...await baseline(), historyOffers: { undo: null, redo: null } }));
      assert.equal(offers.length, readOnly ? 0 : 1);
      assert.equal(h.requests[0]?.allowEdits, !readOnly);
      if (!readOnly) {
        assert.equal(offers[0]?.owner.epoch, h.requests[0]?.owner.epoch);
        assert.equal(offers[0]?.projectRevision, h.requests[0]?.projectRevision);
        assert.equal(offers[0]?.documentRevision, h.requests[0]?.documentRevision);
      }
    } finally { h.controller.close(); }
  }
});

test("edit permission follows the bound server state and changes only after its save acknowledgement", async () => {
  const h = harness();
  let access = { revision: 5, readOnly: true };
  h.api.access = () => Promise.resolve(access);
  h.api.setAccess = (revision, readOnly) => {
    assert.equal(revision, access.revision);
    access = { revision: revision + 1, readOnly };
    return Promise.resolve(access);
  };
  try {
    await h.controller.init();
    assert.equal(h.controller.view.flags.allowEdits, false);
    h.controller.flags({ allowEdits: true, allowWeb: false });
    assert.equal(h.controller.view.flags.allowEdits, false);
    await wait();
    assert.equal(h.controller.view.flags.allowEdits, true);
    access = { revision: access.revision + 1, readOnly: true };
    h.controller.draft("Read all facts and sources.");
    await h.controller.send(baseline);
    assert.equal(h.requests[0]?.allowEdits, false);
    assert.equal(h.requests[0]?.scope.kind, "resume");
    h.api.setAccess = () => Promise.reject(new AgentApiFailure("AGENT_SETTINGS_CONFLICT"));
    h.controller.flags({ allowEdits: true, allowWeb: false });
    await wait();
    assert.equal(h.controller.view.flags.allowEdits, false);
    assert.equal(h.controller.view.error, "AGENT_SETTINGS_CONFLICT");
  } finally { h.controller.close(); }
});
function baseline(): Promise<{ response: RichProjectResponse; scope: { kind: "resume" } }> {
  const workspace: unknown = structuredClone(fixture); assert.ok(validateRichWorkspaceShape(workspace));
  return Promise.resolve({ response: { workspace, durability: "durable", savedProjectRevision: 1, savedDocumentRevision: 1, saveError: null, generation: null }, scope: { kind: "resume" } });
}
function harness(heartbeatMs = 5000) {
  let settings: AgentSettings = { schemaVersion: 1, revision: 2, enabled: true, selectedAgentModel: "model_a" };
  const owner = { token: "synthetic_owner_capability_0123456789", epoch: 1 };
  const requests: AgentRunRequest[] = [], runs = new Map<string, AgentRun>(), applied: string[] = [], sequences: number[] = [];
  let submitted = 0, lostReply = false, renewFails = false, closes = 0, cancelled = 0;
  const capabilities = (): AgentCapabilities => ({ schemaVersion: 1, ready: true, binaryVersion: "fixture", binarySha256: "a".repeat(64),
    protocolSha256: "b".repeat(64), configSha256: "c".repeat(64), connectionEpoch: "account_1", modes: ["edit", "check_only"], tools: [], webAvailable: true,
    models: ["model_a", "model_b"].map(model => ({ model, state: "unverified", binarySha256: "a".repeat(64), protocolSha256: "b".repeat(64),
      configSha256: "c".repeat(64), accountEpoch: "account_1", reason: null })), unavailable: null });
  const lease = { projectId: "project-1", sessionId: "history_1", owner, expiresAt: "2026-10-15T12:00:15Z" };
  let current: AgentRun | null = null;
  let eventScript: (after: number, signal: AbortSignal) => AsyncGenerator<AgentEvent> = async function* () {};
  const api: AssistantApi = {
    projectId: "project-1", settings: () => Promise.resolve(settings),
    saveSettings: request => { settings = { schemaVersion: 1, revision: settings.revision + 1, enabled: request.enabled, selectedAgentModel: request.selectedAgentModel }; return Promise.resolve(settings); },
    capabilities: () => Promise.resolve(capabilities()), conversations: () => Promise.resolve({ items: [{ id: "conversation_1", createdAt: now, updatedAt: now, title: "Saved", activeRunId: null }], nextCursor: null }),
    conversation: () => Promise.resolve({ schemaVersion: 1, id: "new_conversation", projectId: "project-1", createdAt: now, updatedAt: now, messages: [], runs: [], sources: [], findings: [] }),
    messages: () => Promise.resolve({ items: [], nextCursor: null }), resources: () => Promise.resolve({ sources: [], findings: [], nextCursor: null }),
    open: () => Promise.resolve(lease), renew: () => renewFails ? Promise.reject(new AgentApiFailure("AGENT_LEASE_EXPIRED", 409)) : Promise.resolve(lease),
    close: () => { closes++; if (current && !["completed", "cancelled"].includes(current.state)) current = { ...current, state: "interrupted", finishedAt: now, error: { code: "AGENT_LEASE_EXPIRED" } }; return Promise.resolve({}); },
    submit: request => {
      requests.push(structuredClone(request));
      let run = runs.get(request.clientRequestId);
      if (!run) {
        submitted++;
        run = { id: "run_1", conversationId: request.conversationId, projectId: "project-1", clientRequestId: request.clientRequestId,
          ownerEpoch: 1, state: "running", allowEdits: request.allowEdits, allowWeb: request.allowWeb, scope: request.scope,
          model: settings.selectedAgentModel ?? "missing", connectionEpoch: "account_1", settingsRevision: request.settingsRevision,
          createdAt: now, deadline: "2026-10-15T12:03:50Z", finishedAt: null, usage: null, error: null, savedBatchId: null, outcomeUnknown: false };
        runs.set(request.clientRequestId, run); current = run;
      }
      if (lostReply) { lostReply = false; return Promise.reject(new Error("Lost reply")); }
      return Promise.resolve(run);
    }, read: () => { assert.ok(current); return Promise.resolve({ run: current, receipts: [] }); },
    cancel: () => { cancelled++; assert.ok(current); current = { ...current, state: "cancelled", finishedAt: now, error: { code: "AGENT_CANCELLED" } }; return Promise.resolve(current); },
    events: async function* (_run, _owner, after, signal) { sequences.push(after); yield* eventScript(after, signal); },
    prepared: () => ({ claim: () => Promise.reject<AgentClaimResult>(new Error("No claim expected")), commit: () => Promise.reject<AgentCommitResult>(new Error("No commit expected")), recover: () => Promise.resolve(null), report: () => Promise.resolve() }),
  };
  const controller = new AssistantController(api, { sessionId: "history_1", apply: id => { applied.push(id); return Promise.resolve(); } }, () => {}, heartbeatMs);
  const event = (sequence: number, type: "message.delta" | "edit.offered" | "run.state_changed"): AgentEvent => {
    const common = { schemaVersion: 1 as const, id: "event_" + String(sequence), sequence, projectId: "project-1", conversationId: "conversation_1", runId: "run_1", timestamp: now };
    if (type === "message.delta") return { ...common, type, payload: { text: "Привет 😀" } };
    if (type === "edit.offered") return { ...common, type, payload: { batchId: "batch_1", disposition: "offered", error: null } };
    return { ...common, type, payload: { state: "completed", error: null, savedBatchId: null, outcomeUnknown: false } };
  };
  return { controller, api, requests, applied, sequences, event,
    script: (script: typeof eventScript) => { eventScript = script; }, lose: () => { lostReply = true; },
    expire: () => { renewFails = true; }, finish: () => { assert.ok(current); current = { ...current, state: "completed", finishedAt: now }; },
    counts: () => ({ submitted, closes, cancelled }) };
}

for (const phase of ["metadata", "owner", "baseline", "history", "submit"] as const) {
  test(`Stop fences a send while waiting for ${phase}`, async () => {
    const h = harness(), reached = deferred<void>(), release = deferred<void>();
    const hold = async () => { reached.resolve(); await release.promise; };
    try {
      await h.controller.init(); h.controller.draft("Keep this draft");
      if (phase === "metadata") { const original = h.api.settings; h.api.settings = async () => { await hold(); return original(); }; }
      if (phase === "owner") { const original = h.api.open; h.api.open = async session => { await hold(); return original(session); }; }
      if (phase === "history") h.api.offerHistory = async () => { await hold(); return {}; };
      if (phase === "submit") { const original = h.api.submit; h.api.submit = async request => { const value = await original(request); await hold(); return value; }; }
      const sending = h.controller.send(async () => {
        if (phase === "baseline") await hold();
        return { ...await baseline(), historyOffers: { undo: null, redo: null } };
      });
      await reached.promise; await h.controller.stop(); release.resolve(); await sending;
      assert.equal(h.counts().submitted, phase === "submit" ? 1 : 0);
      assert.equal(h.controller.view.draft, "Keep this draft");
      assert.equal(h.controller.view.pendingSend, false);
      assert.equal(h.controller.active, false);
      if (phase === "submit") assert.equal(h.counts().cancelled, 1);
    } finally { release.resolve(); h.controller.close(); }
  });
}

test("assistant technical Send retry keeps its request identity across settings changes", async () => {
  const h = harness();
  try {
    await h.controller.init(); h.controller.draft("Keep the original request"); h.lose();
    await h.controller.send(baseline);
    assert.equal(h.controller.view.draft, "Keep the original request"); assert.equal(h.controller.view.pendingSend, true);
    await h.controller.chooseModel("model_b");
    h.script(async function* () { h.finish(); yield h.event(1, "run.state_changed"); });
    await h.controller.send(baseline); await wait();
    assert.equal(h.requests.length, 2); assert.deepEqual(h.requests[1], h.requests[0]);
    assert.equal(h.counts().submitted, 1); assert.equal(h.controller.view.run?.model, "model_a");
    assert.equal(h.controller.view.settings?.selectedAgentModel, "model_b");
  } finally { h.controller.close(); }
});

test("assistant reconnect deduplicates deltas and offers without submitting another run", async () => {
  const h = harness();
  try {
    let connection = 0;
    h.script(async function* () {
      connection++;
      yield h.event(1, "message.delta"); yield h.event(2, "edit.offered");
      if (connection === 1) throw new Error("Stream dropped");
      h.finish(); yield h.event(3, "run.state_changed");
    });
    await h.controller.init(); h.controller.draft("Check and edit"); await h.controller.send(baseline);
    for (let i = 0; i < 100 && h.sequences.length < 2; i++) await new Promise<void>(resolve => { setTimeout(resolve, 5); });
    await wait();
    assert.deepEqual(h.sequences.slice(0, 2), [0, 2]); assert.deepEqual(h.applied, ["batch_1"]);
    assert.equal(h.counts().submitted, 1); assert.equal(h.controller.view.run?.state, "completed");
  } finally { h.controller.close(); }
});

test("assistant Stop cancels separately from aborting its stream and preserves the draft", async () => {
  const h = harness();
  try {
    h.script(async function* (_after, signal) {
      await new Promise<void>(resolve => { signal.addEventListener("abort", () => resolve(), { once: true }); });
    });
    await h.controller.init(); h.controller.draft("Check only"); h.controller.flags({ allowEdits: false, allowWeb: false });
    await h.controller.send(baseline); h.controller.draft("Next turn draft"); await h.controller.stop();
    assert.equal(h.counts().cancelled, 1); assert.equal(h.controller.view.run?.state, "cancelled");
    assert.equal(h.controller.view.draft, "Next turn draft");
    assert.equal(h.requests[0]?.allowEdits, false); assert.equal(h.requests[0]?.allowWeb, false);
  } finally { h.controller.close(); }
});

test("assistant heartbeat loss closes the owner lease and never retries inference", async () => {
  const h = harness(10);
  try {
    h.script(async function* (_after, signal) {
      await new Promise<void>(resolve => { signal.addEventListener("abort", () => resolve(), { once: true }); });
    });
    await h.controller.init(); h.controller.draft("Inspect resume"); await h.controller.send(baseline); h.expire();
    for (let i = 0; i < 50 && !h.counts().closes; i++) await new Promise<void>(resolve => { setTimeout(resolve, 5); });
    assert.equal(h.counts().closes, 1); assert.equal(h.counts().submitted, 1);
    await wait(); assert.equal(h.controller.view.run?.state, "interrupted");
    assert.equal(h.controller.view.error, "AGENT_LEASE_EXPIRED");
  } finally { h.controller.close(); }
});
