import assert from "node:assert/strict";
import test from "node:test";
import { AssistantController } from "../src/assistant/controller";
import { backgroundReply, GlobalJobsApi, JobsApi, type BackgroundRequest } from "../src/background/api";
import { FixedOperations } from "../src/background/fixed";
import { GlobalJobs, type GlobalJobsTransport } from "../src/background/global";
import { ProjectJobs } from "../src/background/jobs";
import { active, jobKey, projectActivity, statusLabel, summary } from "../src/background/status";
import type { JobIndexV1 } from "../src/contracts/generated/background_index_v1";
import type { JobSnapshotV1 } from "../src/contracts/generated/background_snapshot_v1";
import type { RichSelection } from "../src/contracts/generated/rich_selection";
import { RichApiFailure } from "../src/rich/api";
import { selectionChecksum } from "../src/rich/synchronization";
import { assistantApi, jobsHarness, running } from "./support/background-jobs";
import { deferred } from "./support/background-writer";
import { PythonBridge } from "./support/python-bridge";

function globalHarness(initial: JobSnapshotV1[] = [running()]) {
  let rows = initial.map(job => summary(job, "Synthetic resume"));
  const timers = new Map<() => void, number>(), calls = { index: 0, stop: 0, discard: 0 };
  let reply = () => Promise.resolve({ schemaVersion: 1 as const, jobs: structuredClone(rows) });
  let command: (id: string) => Promise<JobSnapshotV1> = id => { const original = initial.find(job => job.id === id); assert.ok(original);
    return Promise.resolve({ ...original, execution: "cancelled" as const, eventCursor: original.eventCursor + 1 }); };
  const registry = new GlobalJobs({ index: () => { calls.index++; return reply(); },
    stop: (_project, id) => { calls.stop++; return command(id); }, discard: (_project, id) => { calls.discard++; return command(id); } },
  { later: (callback, delay) => { timers.set(callback, delay); return () => { timers.delete(callback); }; } });
  return { registry, timers, calls, set: (next: typeof rows) => { rows = next; }, reply: (next: typeof reply) => { reply = next; },
    command: (next: typeof command) => { command = next; }, close: () => { registry.close(); assert.equal(timers.size, 0); } };
}

function realGlobal(bridge: PythonBridge) {
  const api = new GlobalJobsApi(() => bridge.http("/v1/background/jobs")), calls = { stop: 0 };
  const transport: GlobalJobsTransport = { index: () => api.index(), stop: (project, id) => {
    calls.stop++; return bridge.jobs(project).cancel(id); }, discard: (project, id) => bridge.jobs(project).discard(id) };
  const timers = new Set<() => void>(), registry = new GlobalJobs(transport,
    { later: callback => { timers.add(callback); return () => { timers.delete(callback); }; } });
  return { registry, calls, timers, close: () => { registry.close(); assert.equal(timers.size, 0); } };
}

async function rewrite(bridge: PythonBridge, project: string, action: string) {
  const response = (await bridge.writer(project).bootstrap()).response;
  assert.ok(response.workspace.project);
  const selection: RichSelection = { kind: "text", anchor: { blockId: "narrative", cellId: null, offset: 0 },
    head: { blockId: "narrative", cellId: null, offset: 6 }, blockIds: ["narrative"],
    capture: { sessionId: "nb06-global", actionId: action, actionToken: 0, dependencies: [] }, textSha256: "0".repeat(64) };
  selection.textSha256 = await selectionChecksum(response.workspace.project.document, selection);
  return new FixedOperations(project, bridge.jobs(project)).submit({ kind: "rewrite", request: { selection, instruction: "Clarify" } });
}

async function agent(bridge: PythonBridge, ready: { project: string; conversation: string }, allowEdits = false) {
  const api = bridge.jobs(ready.project), index = await api.projectJobs(), workspace = (await bridge.writer(ready.project).bootstrap()).response.workspace;
  assert.ok(workspace.project);
  return api.submit({ schemaVersion: 1, lineage: index.lineage, requestEpoch: index.requestEpoch,
    request: { clientRequestId: crypto.randomUUID(), conversationId: ready.conversation, message: "Check this synthetic resume",
      allowEdits, allowWeb: false, scope: { kind: "resume" }, settingsRevision: 2,
      projectRevision: workspace.projectRevision, documentRevision: workspace.documentRevision, factsRevision: workspace.project.facts.revision } });
}

test("NB-W13:v02 old generation and cursor cannot regress global or project state", async () => {
  const newest = { ...running(), executionGeneration: 2, eventCursor: 5 }, h = globalHarness([newest]), p = jobsHarness(undefined, [newest]);
  try {
    await h.registry.refresh(); await p.jobs.refresh();
    h.set([summary({ ...newest, executionGeneration: 1, eventCursor: 99 }, "Old generation")]);
    p.set([{ ...newest, executionGeneration: 1, eventCursor: 99 }]);
    await h.registry.refresh(); await p.jobs.refresh();
    assert.equal(h.registry.view.jobs[0]?.executionGeneration, 2); assert.equal(p.jobs.view.project?.jobs[0]?.executionGeneration, 2);
    h.set([summary({ ...newest, eventCursor: 1 }, "Old cursor")]); await h.registry.refresh();
    assert.equal(h.registry.view.jobs[0]?.eventCursor, 5); assert.equal(h.registry.view.notices.length, 0);
    assert.equal(p.calls.cancel, 0);
  } finally { h.close(); p.close(); }
});

test("global notices are bounded, deduplicated and quiet for historical or automatic results", async () => {
  const jobs = Array.from({ length: 6 }, (_, i) => running(`notice-${String(i)}`)), h = globalHarness(jobs);
  try {
    await h.registry.refresh();
    const completed = jobs.map(job => ({ ...summary(job, job.id), execution: "failed" as const, eventCursor: job.eventCursor + 1 }));
    h.set(completed); await h.registry.refresh(); assert.equal(h.registry.view.notices.length, 3);
    const notices = structuredClone(h.registry.view.notices); await h.registry.refresh(); assert.deepEqual(h.registry.view.notices, notices);
    for (const notice of notices) h.registry.dismiss(notice.key);
    await h.registry.refresh(); assert.equal(h.registry.view.notices.length, 0);
    const silent = { ...completed[0]!, kind: "reconciliation" as const, execution: "completed" as const,
      publication: "saved" as const, saved: true, eventCursor: 50 };
    h.set([silent]); await h.registry.refresh(); assert.equal(h.registry.view.notices.length, 0);
    const historical = globalHarness([{ ...jobs[0]!, execution: "failed" }]);
    try { await historical.registry.refresh(); assert.equal(historical.registry.view.notices.length, 0); } finally { historical.close(); }
  } finally { h.close(); }
});

test("disabled global polling stops; transient errors preserve the last known jobs", async () => {
  const h = globalHarness(); const unsubscribe = h.registry.subscribe(() => {});
  try {
    await h.registry.refresh(); assert.deepEqual([...h.timers.values()], [700]); const known = structuredClone(h.registry.view.jobs);
    h.reply(() => Promise.reject(new Error("Synthetic lost reply")));
    await assert.rejects(h.registry.refresh(), /Synthetic lost reply/u); assert.deepEqual(h.registry.view.jobs, known);
    h.reply(() => Promise.reject(new RichApiFailure("JOB_DISABLED")));
    await assert.rejects(h.registry.refresh(), /JOB_DISABLED/u); assert.equal(h.registry.view.enabled, false); assert.equal(h.timers.size, 0);
    const calls = h.calls.index; unsubscribe(); assert.equal(h.calls.index, calls);
  } finally { unsubscribe(); h.close(); }
});

test("Stop deduplicates an exact job and fences a stale index reply", async () => {
  const first = running("first"), second = running("second"), h = globalHarness([first, second]);
  const held = deferred<JobIndexV1>(), cancel = deferred<JobSnapshotV1>();
  try {
    await h.registry.refresh(); const row = h.registry.view.jobs[0]; assert.ok(row);
    const old = structuredClone(h.registry.view.jobs); h.reply(() => held.promise); const refreshing = h.registry.refresh();
    h.command(() => cancel.promise); const stopping = h.registry.command(row, "stop");
    assert.equal(h.registry.command(row, "stop"), stopping);
    cancel.resolve({ ...first, execution: "cancelled", eventCursor: 5 }); await stopping;
    held.resolve({ schemaVersion: 1, jobs: old }); await refreshing;
    assert.equal(h.registry.view.jobs[0]?.execution, "cancelled"); assert.equal(h.registry.view.jobs[1]?.execution, "running"); assert.equal(h.calls.stop, 1);
    assert.equal(h.registry.view.notices.length, 1);
  } finally { held.resolve({ schemaVersion: 1, jobs: [] }); cancel.resolve(first); h.close(); }
});

test("a late command result cannot resurrect a deleted global row", async () => {
  const h = globalHarness(), held = deferred<JobSnapshotV1>();
  try {
    await h.registry.refresh(); const row = h.registry.view.jobs[0]; assert.ok(row);
    h.command(() => held.promise); const stopping = h.registry.command(row, "stop");
    h.set([]); await h.registry.refresh(); assert.equal(h.registry.view.jobs.length, 0);
    held.resolve({ ...running(), execution: "cancelled", eventCursor: 3 }); await stopping;
    assert.equal(h.registry.view.jobs.length, 0); assert.equal(h.registry.view.notices.length, 0);
  } finally { held.resolve(running()); h.close(); }
});

for (const variant of ["NB-W13:v01", "NB-W13:v03", "NB-W13:v04"] as const) {
  test(`${variant} real replay resync survives ${variant.endsWith("01") ? "a missing sequence" : variant.endsWith("03") ? "a pruned cursor" : "terminal before an older event"} without inference`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false, jobs: ProjectJobs | null = null;
    const held = await bridge.hold("scripted_model_ready", "job"); t.after(() => bridge.close(!passed));
    try {
      const accepted = await agent(bridge, ready); await held.reached;
      const api = bridge.jobs(ready.project), early = await api.replay(accepted.id, 1, 0);
      await held.release(); await bridge.call({ kind: "wait_job", job: accepted.id });
      const terminal = await api.read(accepted.id); assert.equal(terminal.execution, "completed");
      if (variant.endsWith("03")) await bridge.call({ kind: "prune_events", job: accepted.id });
      let reads = 0, gaps = 0;
      const fault: BackgroundRequest = async (path, method, body) => {
        const raw = await bridge.transport(path, method, body);
        if (path.endsWith("/read")) reads++;
        if (!path.endsWith("/replay")) return raw;
        const replay = await backgroundReply("background_replay_v1", raw);
        if (variant.endsWith("01")) return { ...replay, events: replay.events.slice(1) };
        if (variant.endsWith("04")) {
          const old = early.events[0], latest = replay.events.at(-1); assert.ok(old && latest); assert.ok(latest.cursor > old.cursor);
          return { ...replay, events: [latest, old] };
        }
        gaps += replay.events.filter(event => event.type === "cursor.gap").length; return replay;
      };
      jobs = new ProjectJobs(new JobsApi(ready.project, fault), { later: () => () => {} });
      await jobs.refresh(); assert.deepEqual(jobs.view.project?.jobs, [terminal]);
      if (variant.endsWith("03")) assert.equal(gaps, 1); else assert.equal(reads, 1);
      await jobs.refresh(); assert.deepEqual(jobs.view.project?.jobs, [terminal]);
      const stats = await bridge.call({ kind: "stats" }); assert.ok(typeof stats === "object" && stats !== null && "syntheticStarts" in stats);
      assert.equal(stats.syntheticStarts, 1); assert.equal(terminal.publication, "none"); passed = true;
    } finally { await held.release(); jobs?.close(); await bridge.close(!passed); }
  });
}

test("NB-W13:v05 execution completes before Saved; later publication emits one notice and no new inference", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; const h = realGlobal(bridge);
  const held = await bridge.hold("before_commit_claim", "writer", { jobOnly: true }); t.after(() => bridge.close(!passed));
  try {
    await bridge.call({ kind: "fixed_fixture" }); await h.registry.refresh();
    const reply = await rewrite(bridge, ready.project, "later-saved"); await held.reached;
    await bridge.call({ kind: "wait_execution", job: reply.job.id }); await h.registry.refresh();
    const before = h.registry.view.jobs[0]; assert.ok(before); assert.equal(before.execution, "completed"); assert.equal(before.saved, false);
    assert.notEqual(statusLabel(before), "Сохранено"); assert.equal(h.registry.view.notices.length, 0);
    await held.release(); await bridge.call({ kind: "wait_fixed", job: reply.job.id }); await h.registry.refresh();
    assert.equal(h.registry.view.jobs[0]?.saved, true); assert.equal(h.registry.view.notices.length, 1);
    await h.registry.refresh(); assert.equal(h.registry.view.notices.length, 1);
    const stats = await bridge.call({ kind: "stats" }); assert.ok(typeof stats === "object" && stats !== null && "fixedStarts" in stats);
    assert.equal(stats.fixedStarts, 1); passed = true;
  } finally { await held.release(); h.close(); await bridge.close(!passed); }
});

for (const [variant, screen] of [["NB-W13:v06", "New"], ["NB-W13:v07", "Settings"], ["NB-W13:v08", "another conversation"]] as const) {
  test(`${variant} ${screen} keeps real background work and exact result identity`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false, controller: AssistantController | null = null;
    const h = realGlobal(bridge), api = bridge.jobs(ready.project), jobs = new ProjectJobs(api, { later: () => () => {} });
    const held = await bridge.hold("scripted_model_ready", "job"); t.after(() => bridge.close(!passed));
    let unsubProject = () => {}, unsubGlobal = () => {};
    try {
      const accepted = await agent(bridge, ready); await held.reached;
      unsubGlobal = h.registry.subscribe(() => {}); unsubProject = jobs.subscribe(() => {});
      await h.registry.refresh(); await jobs.refresh();
      if (screen === "New") unsubProject();
      if (screen === "another conversation") {
        const metadata = assistantApi(ready.project);
        metadata.api.conversations = async () => ({ items: [{ id: ready.conversation, createdAt: accepted.createdAt,
          updatedAt: accepted.updatedAt, title: "Synthetic", activeRunId: accepted.id }], nextCursor: null });
        controller = new AssistantController(metadata.api, { sessionId: "screen-test", apply: () => Promise.reject(new Error("Legacy publication reached")) }, () => {}, 5000, jobs);
        await controller.init(); await controller.newConversation(); await controller.select(ready.conversation); controller.close();
        assert.deepEqual(metadata.calls, { lease: 0, cancel: 0 });
      }
      await held.release(); await bridge.call({ kind: "wait_job", job: accepted.id }); await h.registry.refresh(); await jobs.refresh();
      const row = h.registry.view.jobs[0]; assert.ok(row); assert.equal(row.projectId, ready.project); assert.equal(row.jobId, accepted.id);
      assert.equal(row.execution, "completed"); assert.equal(row.saved, false); assert.equal(row.publication, "none");
      assert.equal(h.registry.view.notices.length, 1); assert.equal(h.registry.view.notices[0]?.kind, "completed");
      await h.registry.refresh(); assert.equal(h.registry.view.notices.length, 1);
      assert.equal(h.calls.stop, 0); assert.equal(jobs.view.project?.jobs[0]?.id, accepted.id);
      assert.equal((await api.conversation(accepted.id)).id, ready.conversation); passed = true;
    } finally { await held.release(); controller?.close(); unsubProject(); unsubGlobal(); jobs.close(); h.close(); await bridge.close(!passed); }
  });
}

test("a real Saved receipt remains visible after exact Stop cancels the remaining execution", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; const h = realGlobal(bridge);
  const held = await bridge.hold("scripted_after_apply", "job"); t.after(() => bridge.close(!passed));
  try {
    await h.registry.refresh(); const accepted = await agent(bridge, ready, true); await held.reached;
    await bridge.call({ kind: "wait_publication", job: accepted.id, publication: "saved" }); await h.registry.refresh();
    const row = h.registry.view.jobs[0]; assert.ok(row?.saved); assert.ok(active(row)); assert.match(statusLabel(row), /Сохранено/u);
    const before = await bridge.call({ kind: "stats" }); assert.ok(typeof before === "object" && before !== null && "workspaceSha256" in before);
    await h.registry.command(row, "stop"); await held.release(); await bridge.call({ kind: "wait_job", job: accepted.id }); await h.registry.refresh();
    const cancelled = h.registry.view.jobs[0]; assert.ok(cancelled); assert.equal(cancelled.execution, "cancelled"); assert.equal(cancelled.saved, true);
    assert.match(statusLabel(cancelled), /Сохранено.*остановлено/u); assert.equal(h.calls.stop, 1);
    assert.equal(h.registry.view.notices.length, 1); assert.equal(h.registry.view.notices[0]?.kind, "cancelled");
    const after = await bridge.call({ kind: "stats" }); assert.ok(typeof after === "object" && after !== null && "workspaceSha256" in after);
    assert.equal(after.workspaceSha256, before.workspaceSha256); assert.equal(jobKey(row), jobKey(cancelled));
    assert.equal(projectActivity(h.registry.view.jobs).size, 0); passed = true;
  } finally { await held.release(); h.close(); await bridge.close(!passed); }
});

test("discarding a real conflicted result clears its review notice and preserves resume content", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; const h = realGlobal(bridge);
  const held = await bridge.hold("fixed_model_ready", "job"); t.after(() => bridge.close(!passed));
  try {
    await bridge.call({ kind: "fixed_fixture" }); await h.registry.refresh();
    const before = (await bridge.writer(ready.project).bootstrap()).response.workspace.project;
    const reply = await rewrite(bridge, ready.project, "conflict-to-discard"); await held.reached;
    await bridge.http(`/v1/rich/projects/${ready.project}/cancel-action`, "POST", {
      sessionId: "nb06-global", actionId: "conflict-to-discard", actionToken: 0, dependencies: [] });
    await held.release(); await bridge.call({ kind: "wait_fixed", job: reply.job.id }); await h.registry.refresh();
    const row = h.registry.view.jobs[0]; assert.ok(row); assert.equal(row.publication, "needs_review");
    assert.equal(h.registry.view.notices[0]?.kind, "review");
    await h.registry.command(row, "discard"); assert.equal(h.registry.view.jobs[0]?.publication, "discarded");
    assert.equal(h.registry.view.notices.length, 0);
    const after = (await bridge.writer(ready.project).bootstrap()).response.workspace.project;
    assert.deepEqual(after?.document, before?.document); assert.deepEqual(after?.facts, before?.facts); passed = true;
  } finally { await held.release(); h.close(); await bridge.close(!passed); }
});
