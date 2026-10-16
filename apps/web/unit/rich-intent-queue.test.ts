import assert from "node:assert/strict";
import test from "node:test";
import { AppliedIntentFailure, IntentQueue, type IntentState } from "../src/rich/intent-queue";
import { currentPanelIntent, technologyKey } from "../src/rich/panel-intents";
import type { PanelCommand } from "../src/rich/synchronization";
import type { WorkingFacts } from "../src/contracts/generated/working_facts";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import { validateRichWorkspaceShape } from "../src/rich/validate";

function gate() { let release = () => {}; const wait = new Promise<void>(resolve => { release = resolve; }); return { wait, release }; }
test("FIFO waits for acknowledgment and drains before navigation", async () => {
  const entered = gate(), durable = gate(), order: string[] = [];
  let state: IntentState<string> = { pending: [], paused: false };
  const queue = new IntentQueue<string>(async name => { order.push(`start ${name}`); if (name === "A") { entered.release(); await durable.wait; } order.push(`saved ${name}`); }, value => { state = value; });
  const a = queue.enqueue("A"), b = queue.enqueue("B"); await entered.wait;
  assert.deepEqual(order, ["start A"]); assert.equal(queue.busy, true); assert.deepEqual(state.pending, ["A", "B"]);
  const navigation = queue.drain().then(() => order.push("navigate")); durable.release(); await Promise.all([a, b, navigation]);
  assert.deepEqual(order, ["start A", "saved A", "start B", "saved B", "navigate"]); assert.equal(queue.busy, false);
});
for (const failed of ["A", "B"]) test(`failed ${failed} drops unsent work and accepts an explicit fresh retry`, async () => {
  const entered = gate(), release = gate(), applied: string[] = [];
  let fail = true;
  const queue = new IntentQueue<string>(async name => { if (name === failed && fail) { entered.release(); await release.wait; throw new Error("preview failed"); } applied.push(name); }, () => {});
  const tasks = [queue.enqueue("A"), queue.enqueue("B"), queue.enqueue("C")];
  const settled = Promise.allSettled(tasks); await entered.wait; const drain = assert.rejects(queue.drain(), /preview failed/); release.release();
  await settled; await drain; assert.deepEqual(applied, failed === "A" ? [] : ["A"]); assert.equal(queue.busy, false);
  fail = false; await queue.enqueue(failed); await queue.drain(); assert.equal(applied.at(-1), failed);
});
test("applied save failure pauses, retains local state and retries only persistence once", async () => {
  const entered = gate(), release = gate(), order: string[] = [];
  let state: IntentState<string> = { pending: [], paused: false }, recoveries = 0;
  const queue = new IntentQueue<string>(async name => {
    order.push(`apply ${name}`);
    if (name === "A") { entered.release(); await release.wait; throw new AppliedIntentFailure(async () => { recoveries++; order.push("save A"); }, new Error("disk full")); }
  }, value => { state = value; });
  const a = queue.enqueue("A"); const rejected = assert.rejects(a, AppliedIntentFailure);
  const b = queue.enqueue("B"); await entered.wait; const navigation = assert.rejects(queue.drain(), AppliedIntentFailure); release.release();
  await rejected; await navigation; assert.equal(state.paused, true); assert.deepEqual(order, ["apply A"]);
  await assert.rejects(queue.enqueue("C"), AppliedIntentFailure);
  await Promise.all([queue.drain(), queue.drain()]); await b;
  assert.equal(recoveries, 1); assert.deepEqual(order, ["apply A", "save A", "apply B"]); assert.equal(queue.busy, false);
});
test("session closure rejects queued work and suppresses late callbacks", async () => {
  const entered = gate(), release = gate(), applied: string[] = [], states: IntentState<string>[] = [];
  const queue = new IntentQueue<string>(async name => { applied.push(name); entered.release(); await release.wait; }, state => states.push(state));
  const settled = Promise.allSettled([queue.enqueue("A"), queue.enqueue("B")]); await entered.wait; queue.close(); const count = states.length; release.release();
  assert.ok((await settled).every(result => result.status === "rejected")); await assert.rejects(queue.drain(), /закрыт/);
  assert.deepEqual(applied, ["A"]); assert.equal(states.length, count);
});
test("dequeued technologies normalize duplicates, clear the latest scope and reject a deleted owner", () => {
  const workspace: unknown = structuredClone(fixture); assert.ok(validateRichWorkspaceShape(workspace)); assert.ok(workspace.project);
  const facts: WorkingFacts = workspace.project.facts;
  const parsed: unknown = { id: "technology-a", revision: 1, kind: "technology", origin: "user", evidence: [], userCorrected: true,
    jobId: null, subprojectId: null, canonicalId: { revision: 1, value: null, rawText: "", status: "unknown", pendingRawText: null, userCorrected: false },
    display: { revision: 1, value: "Custom Kit", rawText: "Custom Kit", status: "known", pendingRawText: null, userCorrected: true } };
  const validated: unknown = { ...fixture, project: { ...fixture.project, facts: { ...fixture.project.facts, records: [...fixture.project.facts.records, parsed] } } };
  assert.ok(validateRichWorkspaceShape(validated)); assert.ok(validated.project);
  const technology = validated.project.facts.records.at(-1); assert.ok(technology?.kind === "technology");
  facts.records.push(technology);
  assert.equal(currentPanelIntent({ operation: "add", recordKind: "technology", values: { display: " custom   KIT " } }, facts), null);
  const clear: PanelCommand = { operation: "clear_technologies", recordKind: "technology", jobId: null, recordId: null, periodId: null, values: {} };
  assert.deepEqual(currentPanelIntent(clear, facts), clear);
  assert.throws(() => currentPanelIntent({ ...clear, jobId: "deleted-job" }, facts), /удалена/);
  assert.equal(technologyKey("  Custom \n Kit  "), "custom kit");
});
