import assert from "node:assert/strict";
import test from "node:test";
import { FixedOperations, operationSync, type FixedCommand } from "../src/background/fixed";
import { backgroundReply } from "../src/background/api";
import type { JobFixedReplyV1 } from "../src/contracts/generated/background_fixed_reply_v1";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import type { RichSelection } from "../src/contracts/generated/rich_selection";
import { selectionChecksum } from "../src/rich/synchronization";
import { deferred } from "./support/background-writer";
import { PythonBridge } from "./support/python-bridge";
import { RichApiFailure } from "../src/rich/api";

async function command(response: RichProjectResponse, variant: string, second: boolean): Promise<FixedCommand> {
  const capture = { sessionId: "fixed-cross-layer", actionId: second ? "fixed-cross-layer:2" : "fixed-cross-layer:1", actionToken: 0, dependencies: [] };
  if (variant === "NB-F01:v01") return { kind: "completion", request: { capture,
    blockIds: [second ? "language" : "title"], movedIds: [], removedFields: [], removedRecordIds: [], interpret: false } };
  if (variant === "NB-F01:v03") return { kind: "panel", request: { capture, recordIds: [second ? "language-1" : "candidate-1"] } };
  if (variant === "NB-F01:v04") return { kind: "retry", syncId: second ? "legacy-quote" : "legacy-narrative", capture };
  const id = second ? "quote" : "narrative", project = response.workspace.project;
  assert.ok(project);
  const selection: RichSelection = { kind: "text", anchor: { blockId: id, cellId: null, offset: 0 },
    head: { blockId: id, cellId: null, offset: 6 }, blockIds: [id], capture, textSha256: "0".repeat(64) };
  selection.textSha256 = await selectionChecksum(project.document, selection);
  return { kind: "rewrite", request: { selection, instruction: "Clarify" } };
}

for (const cut of ["before metadata", "before server acceptance", "valid metadata delay"] as const) {
  test(`fixed submission validates its capture ${cut}`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start();
    let passed = false, current = true, posts = 0;
    const reached = deferred<void>(), release = deferred<void>();
    t.after(async () => { release.resolve(); await bridge.close(!passed); });
    try {
      await bridge.call({ kind: "fixed_fixture" });
      const response = (await bridge.writer(ready.project).bootstrap()).response, api = bridge.jobs(ready.project);
      const captured = await command(response, "NB-F01:v02", false);
      const client = new FixedOperations(ready.project, {
        projectJobs: async () => { const value = await api.projectJobs();
          if (cut !== "before server acceptance") { reached.resolve(); await release.promise; }
          return value; },
        fixed: async request => { posts++;
          if (cut === "before server acceptance") { reached.resolve(); await release.promise; }
          return api.fixed(request); }
      });
      const submitting = client.submit(captured, () => current);
      void submitting.catch(() => {});
      await reached.promise;
      if (cut === "before metadata") current = false;
      if (cut === "before server acceptance") {
        assert.equal(captured.kind, "rewrite");
        if (captured.kind !== "rewrite") assert.fail("Expected rewrite");
        await bridge.http(`/v1/rich/projects/${ready.project}/cancel-action`, "POST", captured.request.selection.capture);
      }
      release.resolve();
      if (cut === "valid metadata delay") {
        const reply = await submitting;
        const done = await backgroundReply("background_fixed_reply_v1", await bridge.call({ kind: "wait_fixed", job: reply.job.id }));
        assert.equal(done.job.publication, "saved"); assert.equal(posts, 1);
      } else {
        await assert.rejects(submitting, error => error instanceof RichApiFailure && error.code === "STALE_SELECTION");
        assert.equal(posts, cut === "before metadata" ? 0 : 1);
        assert.equal((await api.projectJobs()).jobs.length, 0);
        const stats = await bridge.call({ kind: "stats" });
        assert.ok(typeof stats === "object" && stats !== null && "fixedStarts" in stats && stats.fixedStarts === 0);
      }
      passed = true;
    } finally { release.resolve(); await bridge.close(!passed); }
  });
}

test("concurrent fixed submissions retain one request identity and one model attempt", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start();
  let passed = false;
  t.after(() => bridge.close(!passed));
  try {
    await bridge.call({ kind: "fixed_fixture" });
    const response = (await bridge.writer(ready.project).bootstrap()).response, client = new FixedOperations(ready.project, bridge.jobs(ready.project));
    const captured = await command(response, "NB-F01:v02", false);
    const [first, replay] = await Promise.all([client.submit(captured), client.submit(captured)]);
    assert.equal(first.job.id, replay.job.id);
    const done = await backgroundReply("background_fixed_reply_v1", await bridge.call({ kind: "wait_fixed", job: first.job.id }));
    assert.equal(done.job.publication, "saved"); assert.equal(done.job.attempts.length, 1);
    const stats = await bridge.call({ kind: "stats" });
    assert.ok(typeof stats === "object" && stats !== null && "fixedStarts" in stats && stats.fixedStarts === 1);
    passed = true;
  } finally { await bridge.close(!passed); }
});

for (const variant of Array.from({ length: 6 }, (_, index) => `NB-F01:v${String(index + 1).padStart(2, "0")}`)) {
  test(`fixed reversed replies keep exact operation identity ${variant}`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start();
    let passed = false;
    const releaseA = deferred<void>(), releaseB = deferred<void>();
    t.after(async () => { releaseA.resolve(); releaseB.resolve(); await bridge.close(!passed); });
    try {
      await bridge.call({ kind: "fixed_fixture" });
      const first = (await bridge.writer(ready.project).bootstrap()).response;
      let second = first;
      if (variant === "NB-F01:v05") {
        const cloned = await bridge.call({ kind: "clone" });
        assert.ok(typeof cloned === "object" && cloned !== null && "project" in cloned && typeof cloned.project === "string");
        await bridge.call({ kind: "fixed_fixture", project: cloned.project });
        second = (await bridge.writer(cloned.project).bootstrap()).response;
      }
      const acceptedA = deferred<JobFixedReplyV1>(), acceptedB = deferred<JobFixedReplyV1>();
      function client(response: RichProjectResponse, accepted: ReturnType<typeof deferred<JobFixedReplyV1>>, release: ReturnType<typeof deferred<void>>) {
        const api = bridge.jobs(response.workspace.projectId);
        return new FixedOperations(response.workspace.projectId, { projectJobs: () => api.projectJobs(),
          fixed: async request => { const reply = await api.fixed(request); accepted.resolve(reply); await release.promise; return reply; } });
      }
      const order: string[] = [];
      const a = client(first, acceptedA, releaseA).submit(await command(first, variant, false)).then(reply => { order.push("A"); return reply; });
      const submittedA = await acceptedA.promise;
      const b = client(second, acceptedB, releaseB).submit(await command(second, variant, true)).then(reply => { order.push("B"); return reply; });
      const submittedB = await acceptedB.promise;
      const doneA = await backgroundReply("background_fixed_reply_v1", await bridge.call({ kind: "wait_fixed", project: first.workspace.projectId, job: submittedA.job.id }));
      const doneB = await backgroundReply("background_fixed_reply_v1", await bridge.call({ kind: "wait_fixed", project: second.workspace.projectId, job: submittedB.job.id }));
      assert.equal(doneA.job.publication, "saved"); assert.equal(doneB.job.publication, "saved");
      releaseB.resolve(); const replyB = await b;
      releaseA.resolve(); const replyA = await a;
      assert.deepEqual(order, ["B", "A"]);
      assert.equal(replyA.job.id, submittedA.job.id); assert.equal(replyB.job.id, submittedB.job.id);
      assert.notEqual(replyA.syncId, replyB.syncId); assert.notEqual(replyA.actionId, replyB.actionId);
      const viewA = await bridge.writer(first.workspace.projectId).bootstrap(), viewB = await bridge.writer(second.workspace.projectId).bootstrap();
      assert.equal(operationSync(viewA.response, first.workspace.projectId, "fixed-cross-layer:1").id, replyA.syncId);
      assert.equal(operationSync(viewB.response, second.workspace.projectId, "fixed-cross-layer:2").id, replyB.syncId);
      if (variant !== "NB-F01:v05") {
        for (const response of [viewA.response, viewB.response]) {
          assert.ok(response.workspace.syncRecords.some(record => record.id === replyA.syncId));
          assert.ok(response.workspace.syncRecords.some(record => record.id === replyB.syncId));
        }
      } else assert.throws(() => operationSync(viewB.response, first.workspace.projectId, "fixed-cross-layer:1"), /INVALID_RESULT/u);
      assert.equal(doneA.job.attempts.length, 1); assert.equal(doneB.job.attempts.length, 1);
      assert.ok(doneA.job.attempts.every(attempt => attempt.cleanupVerified) && doneB.job.attempts.every(attempt => attempt.cleanupVerified));
      passed = true;
    } finally { releaseA.resolve(); releaseB.resolve(); await bridge.close(!passed); }
  });
}
