import assert from "node:assert/strict";
import test from "node:test";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import type { AgentClaimResult } from "../src/contracts/generated/agent_claim_result";
import type { AgentCommitResult } from "../src/contracts/generated/agent_commit_result";
import type { AgentEditBatch } from "../src/contracts/generated/agent_edit_batch";
import type { AgentEditReceipt } from "../src/contracts/generated/agent_edit_receipt";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import type { RichMutation } from "../src/contracts/generated/rich_mutation";
import { PreparedEditorBridge, type PreparedApi } from "../src/assistant/editor-bridge";
import { documentCells, type StoredBlock } from "../src/rich/document-cells";
import { factCells } from "../src/rich/fact-cells";
import { SessionHistory, type HistoryEffectContext } from "../src/rich/history";
import { RichSaveQueue } from "../src/rich/save-queue";
import { validateRichWorkspaceShape } from "../src/rich/validate";

function response(): RichProjectResponse {
  const workspace: unknown = structuredClone(fixture);
  assert.ok(validateRichWorkspaceShape(workspace));
  return { workspace, durability: "durable", savedProjectRevision: 1, savedDocumentRevision: 1, saveError: null, generation: null };
}

function harness() {
  const before = response(), after = structuredClone(before), project = after.workspace.project;
  assert.ok(project);
  const title = project.document.regions[0].blocks.find(block => block.id === "title");
  assert.ok(title && Array.isArray(title.content));
  const span = title.content[0]; assert.ok(span?.type === "fact_field");
  span.text = "Architect"; span.syncedFactRevision = 2; title.revision = 2;
  const record = project.facts.records[0]; assert.ok(record?.kind === "candidate");
  record.title = { ...record.title, value: "Architect", rawText: "Architect", revision: 2, userCorrected: true };
  record.revision = 2; project.facts.revision = 2;
  after.workspace.projectRevision = project.revision = 2;
  after.workspace.documentRevision = project.document.revision = 2;
  after.savedProjectRevision = after.savedDocumentRevision = 2;
  const batch: AgentEditBatch = { id: "batch_1", runId: "run_1", toolKey: "prepare_1", ownerEpoch: 1, state: "offered",
    scope: { kind: "resume" }, readSnapshotIds: [], dependencies: [], requestSha256: "c".repeat(64), previewSha256: "d".repeat(64),
    affected: [], factRecordIds: [record.id], mutation: { schemaVersion: 1, projectId: before.workspace.projectId,
      clientMutationId: "agent_mutation_1", actionId: "history_1:agent:action_1", kind: "structure",
      capture: { sessionId: "history_1", actionId: "history_1:agent:action_1", actionToken: 0, dependencies: [] },
      steps: [{ kind: "put_block", parentId: "header", afterId: "name", beforeRevision: 1, block: title, keepChildren: true },
        { kind: "put_record", beforeRevision: 1, record }] } };
  after.workspace.mutationReplay.push({ clientMutationId: batch.mutation.clientMutationId, requestSha256: batch.requestSha256, resultingRevision: 2 });
  const receipt: AgentEditReceipt = { batchId: batch.id, runId: batch.runId, toolKey: batch.toolKey,
    clientMutationId: batch.mutation.clientMutationId, requestSha256: batch.requestSha256, disposition: "saved",
    projectRevision: 2, documentRevision: 2, factsRevision: 2, durable: true, error: null };
  const claim: AgentClaimResult = { ticket: "synthetic_ticket_capability_0123456789", expiresAt: "2026-10-15T00:00:15Z", batch };
  const reply: AgentCommitResult = { receipt, project: after };
  const cache = new Map<string, StoredBlock>();
  const cells = (value: RichProjectResponse) => {
    const current = value.workspace.project; assert.ok(current);
    return new Map([...documentCells(current.document, cache), ...factCells(current.facts)]);
  };
  const mounted = cells(before), effects: HistoryEffectContext[] = [], order: string[] = [];
  let onEffect: (context: HistoryEffectContext) => void = () => {};
  const history = new SessionHistory("history_1", mounted, (changes, context) => {
    effects.push(context); order.push(context.mode);
    changes.forEach(change => mounted.set(change.key, change.after));
    onEffect(context);
  });
  let ordinarySaves = 0, commits = 0, claims = 0, fences = 0;
  let sendManual: (request: RichMutation) => Promise<RichProjectResponse> = () => Promise.reject(new Error("Unexpected second save"));
  const queue = new RichSaveQueue(before, history.session, request => { ordinarySaves++; return sendManual(request); }, () => { order.push("acknowledged"); });
  const editor = new PreparedEditorBridge({ history, queue, flush: async () => { await queue.flush(); return queue.baseline; }, cells,
    preview: () => Promise.resolve(after), enter: () => { order.push("enter"); }, leave: () => { order.push("leave"); },
    retainImages: () => { assert.equal(history.length, 1); order.push("images"); return Promise.resolve(); },
    fence: () => { fences++; order.push("fence"); } });
  const api: PreparedApi = { claim: () => { claims++; return Promise.resolve(claim); },
    commit: () => { commits++; return Promise.resolve(reply); }, recover: () => Promise.resolve(reply),
    report: () => { order.push("reported"); return Promise.resolve(); } };
  return { before, after, batch, receipt, claim, reply, cells, mounted, history, queue, editor, api, effects, order,
    counts: () => ({ ordinarySaves, commits, claims, fences }),
    effect: (callback: (context: HistoryEffectContext) => void) => { onEffect = callback; },
    sender: (callback: (request: RichMutation) => Promise<RichProjectResponse>) => { sendManual = callback; } };
}

test("assistant reservation creates no placeholder and publishes text/facts as one isolated history action", () => {
  const modes: string[] = [];
  const history = new SessionHistory("history_1", new Map([["text", "Old"], ["fact", "Old"], ["other", "Original"]]),
    (_changes, context) => { modes.push(context.mode); });
  history.commit("typing", [{ key: "other", before: "Original", after: "Typed during research" }], "typing");
  const reservation = history.reserve("history_1:agent:action_1"); assert.ok(reservation);
  assert.equal(history.length, 1);
  assert.equal(history.commit("panel", [{ key: "fact", before: "Old", after: "Late sync" }]), null);
  assert.equal(history.undo(), false);
  assert.equal(history.publish(reservation, [{ key: "text", before: "Old", after: "New" }, { key: "fact", before: "Old", after: "New" }]), true);
  assert.equal(history.length, 2);
  assert.equal(history.undo(), true); assert.equal(history.read("text"), "Old"); assert.equal(history.read("fact"), "Old");
  assert.equal(history.read("other"), "Typed during research");
  assert.equal(history.redo(), true); assert.equal(history.read("text"), "New"); assert.equal(history.read("fact"), "New");
  assert.deepEqual(modes, ["ordinary", "prepared", "assistant_history", "assistant_history"]);
});

test("assistant durable reply adopts the exact save without autosave and deduplicates repeated offers", async () => {
  const h = harness();
  await Promise.all([h.editor.apply(h.batch.id, h.api), h.editor.apply(h.batch.id, h.api)]);
  await h.editor.apply(h.batch.id, h.api);
  assert.deepEqual(h.counts(), { ordinarySaves: 0, commits: 1, claims: 1, fences: 0 });
  assert.equal(h.history.length, 1); assert.equal(h.history.position, 1);
  assert.deepEqual(h.mounted, h.cells(h.after));
  assert.equal(h.queue.baseline, h.after);
  assert.deepEqual(h.order, ["enter", "acknowledged", "prepared", "images", "reported", "leave"]);
  assert.equal(h.history.undo(), true); assert.equal(h.history.redo(), true);
  assert.deepEqual(h.effects.map(context => context.mode), ["prepared", "assistant_history", "assistant_history"]);
  await h.queue.flush(); assert.equal(h.counts().ordinarySaves, 0);
});

test("assistant rejected save discards its reservation without history or queued content", async () => {
  const h = harness();
  const failed: AgentEditReceipt = { ...h.receipt, disposition: "save_failed", durable: false,
    projectRevision: null, documentRevision: null, factsRevision: null, error: { code: "AGENT_SAVE_FAILED" } };
  h.api.commit = () => Promise.resolve({ receipt: failed, project: h.before });
  await h.editor.apply(h.batch.id, h.api);
  assert.equal(h.history.length, 0); assert.deepEqual(h.mounted, h.cells(h.before));
  await h.queue.flush(); assert.equal(h.counts().ordinarySaves, 0);
  assert.equal(h.queue.baseline, h.before);
});

test("assistant baseline refresh accepts operation metadata without replacing content or history", async () => {
  const h = harness(), metadata = structuredClone(h.before), project = metadata.workspace.project;
  assert.ok(project);
  metadata.workspace.projectRevision = project.revision = 3;
  metadata.savedProjectRevision = 3;
  h.queue.refreshMetadata(metadata);
  assert.equal(h.queue.baseline.workspace.projectRevision, 3);
  assert.deepEqual(h.mounted, h.cells(h.before)); assert.equal(h.history.length, 0);
  assert.throws(() => h.queue.refreshMetadata(h.after), /AGENT_STALE_READ/);
  await h.queue.flush(); assert.equal(h.counts().ordinarySaves, 0);
});

test("assistant undo and redo use ordinary saves with the saved action identity and no new command", async () => {
  const h = harness(), requests: RichMutation[] = [];
  let revision = 2;
  h.effect(context => {
    if (context.mode !== "assistant_history") return;
    const project = (context.kind === "undo" ? h.before : h.after).workspace.project; assert.ok(project);
    h.queue.update(project.document, context.actionId ?? "missing", context.kind, project.facts);
  });
  h.sender(request => {
    requests.push(request);
    const response = structuredClone(request.kind === "undo" ? h.before : h.after), project = response.workspace.project;
    assert.ok(project);
    revision++;
    response.workspace.projectRevision = project.revision = revision;
    response.workspace.documentRevision = project.document.revision = revision;
    response.savedProjectRevision = response.savedDocumentRevision = revision;
    project.facts.revision = revision;
    response.workspace.mutationReplay = [...h.after.workspace.mutationReplay,
      { clientMutationId: request.clientMutationId, requestSha256: "a".repeat(64), resultingRevision: revision }];
    return Promise.resolve(response);
  });
  await h.editor.apply(h.batch.id, h.api);
  assert.equal(h.history.undo(), true); await h.queue.flush();
  assert.equal(h.history.redo(), true); await h.queue.flush();
  assert.deepEqual(requests.map(request => request.kind), ["undo", "redo"]);
  assert.ok(requests.every(request => request.actionId === h.batch.mutation.actionId && request.capture.sessionId === "history_1"));
  assert.equal(h.history.length, 1); assert.equal(h.counts().commits, 1);
});

test("assistant lost save reply reconciles once and publishes one action without repeating commit", async () => {
  const h = harness(); let calls = 0, reads = 0;
  h.api.commit = () => { calls++; return Promise.reject(new Error("Lost reply")); };
  h.api.recover = () => { reads++; return Promise.resolve(h.reply); };
  await h.editor.apply(h.batch.id, h.api);
  assert.equal(calls, 1); assert.equal(reads, 1); assert.equal(h.history.length, 1);
  assert.deepEqual(h.mounted, h.cells(h.after)); assert.equal(h.counts().ordinarySaves, 0);
});

test("assistant unknown save outcome fences staged content instead of releasing it to autosave", async () => {
  const h = harness();
  h.api.commit = () => Promise.reject(new Error("Lost reply"));
  h.api.recover = () => Promise.resolve(null);
  await assert.rejects(h.editor.apply(h.batch.id, h.api), /AGENT_OUTCOME_UNKNOWN/);
  assert.equal(h.history.length, 0); assert.deepEqual(h.mounted, h.cells(h.before));
  assert.equal(h.history.commit("typing", [{ key: "new", before: null, after: "Unsafe" }]), null);
  await assert.rejects(h.queue.flush(), /AGENT_OUTCOME_UNKNOWN/);
  assert.equal(h.counts().ordinarySaves, 0); assert.equal(h.counts().fences, 1);
  assert.equal(h.order.includes("leave"), false);
});

test("assistant saved result after editor close keeps durable truth without applying old cells", async () => {
  const h = harness(); let release: ((value: AgentCommitResult) => void) | undefined;
  h.api.commit = () => new Promise<AgentCommitResult>(resolve => { release = resolve; });
  const operation = h.editor.apply(h.batch.id, h.api);
  for (let i = 0; i < 20 && !release; i++) await new Promise<void>(resolve => { setImmediate(resolve); });
  assert.ok(release);
  h.editor.close(); release(h.reply);
  await assert.rejects(operation, /AGENT_OUTCOME_UNKNOWN/);
  assert.equal(h.history.length, 0); assert.deepEqual(h.mounted, h.cells(h.before));
  assert.equal(h.counts().fences, 1);
});
