import assert from "node:assert/strict";
import test from "node:test";
import { ImportTracker, POLL_FAILURES, type ImportApi } from "../src/workbench/import/tracker";
import type { ImportEntry } from "../src/workbench/import/progress";
import type { ProjectTask } from "../src/projects/api";

const task = (projectId: string, id: string, state: ProjectTask["state"] = "running", detail: ProjectTask["detail"] = { operationId: `op-${projectId}` }): ProjectTask => ({
  id, projectId, kind: "import", state, stage: "processing", startedAt: "2026-10-28T00:00:00+00:00", elapsed: 1, detail, error: null });
const flush = async () => { for (let index = 0; index < 5; index++) await new Promise(resolve => setImmediate(resolve)); };

/** A service with one current task per project, a manual poll clock and a log of calls. */
function harness() {
  const current = new Map<string, ProjectTask | null>(), calls: string[] = [], finished: ImportEntry[] = [];
  let failing = false, ticks: (() => void)[] = [], snapshot: ReadonlyMap<string, ImportEntry> = new Map();
  const api: ImportApi = {
    tasks: async projectId => { calls.push(`tasks:${projectId}`); if (failing) throw new Error("REQUEST_FAILED"); const value = current.get(projectId); return value ? [value] : []; },
    cancel: async (projectId, taskId) => { calls.push(`cancel:${projectId}:${taskId}`); const value = task(projectId, taskId, "cancelled"); current.set(projectId, value); return value; },
    resume: async (projectId, operation) => { calls.push(`resume:${projectId}:${operation}`); const value = task(projectId, `${projectId}-resumed`); current.set(projectId, value); return value; },
    start: async (projectId, body) => { calls.push(`start:${projectId}:${body.allowTextRewrite}:${body.effort}`); const value = task(projectId, `${projectId}-started`); current.set(projectId, value); return value; },
    operation: async projectId => { calls.push(`operation:${projectId}`); return null; },
  };
  const tracker = new ImportTracker(entries => { snapshot = entries; }, entry => finished.push(entry),
    { api, now: () => 0, wait: () => new Promise<void>(resolve => { ticks.push(resolve); }) });
  const tick = async () => { const waiting = ticks; ticks = []; waiting.forEach(resolve => resolve()); await flush(); };
  return { tracker, current, calls, finished, tick, entries: () => snapshot, fail: (value: boolean) => { failing = value; } };
}

test("imports of two projects are followed at once and stopping one leaves the other running", async () => {
  const { tracker, current, calls, finished, tick, entries } = harness();
  for (const id of ["a", "b"]) { const value = task(id, `${id}-1`); current.set(id, value); tracker.track(id, value, `${id}.pdf`); }
  await tick();
  assert.deepEqual(calls, ["tasks:a", "tasks:b"]);
  await tracker.stop("a");
  assert.equal(entries().get("a")?.task.state, "cancelled");
  assert.deepEqual(finished.splice(0).map(entry => entry.task.state), ["cancelled"]);
  calls.length = 0;
  current.set("b", task("b", "b-1", "succeeded"));
  await tick();
  assert.deepEqual(calls, ["tasks:b"], "a stopped import is no longer read");
  assert.deepEqual(finished.map(entry => [entry.projectId, entry.task.state]), [["b", "succeeded"]]);
  assert.deepEqual([...entries().keys()], ["a", "b"], "finished imports stay until closed");
  tracker.dismiss("a");
  assert.deepEqual([...entries().keys()], ["b"]);
  tracker.close();
});

test("a task the service lost after a restart continues from its saved operation", async () => {
  const { tracker, current, calls, tick, entries } = harness();
  tracker.track("a", task("a", "a-1"), "a.pdf");
  current.set("a", null);
  await tick();
  assert.deepEqual(calls, ["tasks:a", "resume:a:op-a"]);
  assert.equal(entries().get("a")?.task.id, "a-resumed");
  tracker.close();
});

test("failed reads show a failure after a bound instead of polling forever; Retry reads again", async () => {
  const { tracker, current, calls, tick, entries, fail } = harness();
  const value = task("a", "a-1");
  current.set("a", value); tracker.track("a", value, "a.pdf");
  fail(true);
  for (let index = 0; index < POLL_FAILURES; index++) await tick();
  assert.equal(entries().get("a")?.failure, "REQUEST_FAILED");
  await tick();
  assert.equal(calls.length, POLL_FAILURES, "no read after the failure is shown");
  fail(false);
  await tracker.retry("a");
  await tick();
  assert.equal(entries().get("a")?.failure, null);
  assert.deepEqual(calls.slice(POLL_FAILURES), ["tasks:a"], "Retry after failed reads touches no task");
  tracker.close();
});

test("Retry of a stalled run stops it, then continues the operation; a failed start without one starts again", async () => {
  const { tracker, calls, entries } = harness();
  const stalled = task("a", "a-1", "running", { operationId: "op-a", progress: { phase: "processing", done: 0, total: 1, current: [], events: [],
    lastEventAt: null, lastModelAt: null, quietSeconds: 300, quietLimitSeconds: 245, stalled: true } });
  tracker.track("a", stalled, "a.pdf");
  await tracker.retry("a");
  assert.deepEqual(calls, ["cancel:a:a-1", "resume:a:op-a"]);
  assert.equal(entries().get("a")?.task.id, "a-resumed");
  calls.length = 0;
  tracker.track("b", task("b", "b-1", "failed", {}), "b.pdf", { allowTextRewrite: false, effort: "high" });
  await tracker.retry("b");
  assert.deepEqual(calls, ["operation:b", "start:b:false:high"], "the start keeps the user's own choices");
  tracker.close();
});

test("Retry with no operation and no saved choice starts nothing: the pre-draft screen asks again", async () => {
  const { tracker, calls, entries, finished } = harness();
  tracker.track("a", task("a", "a-1", "failed", {}), "a.pdf");
  finished.length = 0;
  await tracker.retry("a");
  assert.deepEqual(calls, ["operation:a"], "no start with a guessed rewrite choice");
  assert.equal(entries().get("a"), undefined);
  tracker.close();
});

test("a stop whose reply is the finished import runs the finish step like a poll does", async () => {
  const api: ImportApi = { tasks: async () => [], cancel: async (projectId, id) => task(projectId, id, "succeeded"),
    resume: async () => { throw new Error("unused"); }, start: async () => { throw new Error("unused"); }, operation: async () => null };
  const done: ImportEntry[] = [];
  const stopping = new ImportTracker(() => {}, entry => done.push(entry), { api, now: () => 0, wait: () => new Promise<void>(() => {}) });
  stopping.track("a", task("a", "a-1"), "a.pdf");
  await stopping.stop("a");
  assert.deepEqual(done.map(entry => entry.task.state), ["succeeded"]);
  stopping.close();
});

test("Retry leaves a healthy run alone, and a status read for a task Retry replaced meanwhile is dropped", async () => {
  let release: (value: ProjectTask[]) => void = () => {};
  const ticks: (() => void)[] = [], calls: string[] = [];
  const progress = (stalled: boolean) => ({ phase: "processing", done: 0, total: 1, current: [], events: [], lastEventAt: null,
    lastModelAt: null, quietSeconds: stalled ? 300 : 1, quietLimitSeconds: 245, stalled });
  const tracker = new ImportTracker(() => {}, () => {}, { now: () => 0, wait: () => new Promise<void>(resolve => { ticks.push(resolve); }), api: {
    tasks: () => new Promise(resolve => { release = resolve; }), cancel: async (projectId, id) => { calls.push("cancel"); return task(projectId, id, "cancelled"); },
    resume: async projectId => { calls.push("resume"); return task(projectId, "a-2"); }, start: async projectId => task(projectId, "a-3"),
    operation: async () => "op-a" } });
  tracker.track("a", task("a", "a-1", "running", { operationId: "op-a", progress: progress(false) }), "a.pdf");
  await tracker.retry("a");
  assert.deepEqual(calls, [], "a run that is not stalled keeps its task");
  const stalled = task("a", "a-1", "running", { operationId: "op-a", progress: progress(true) });
  tracker.track("a", stalled, "a.pdf");
  ticks.shift()?.(); await flush();
  await tracker.retry("a");
  assert.deepEqual(calls, ["cancel", "resume"]);
  assert.equal(tracker.get("a")?.task.id, "a-2");
  release([stalled]); await flush();
  assert.equal(tracker.get("a")?.task.id, "a-2", "the late read of a-1 does not replace a-2");
  tracker.close();
});
