import assert from "node:assert/strict";
import test from "node:test";
import { AssistantController } from "../src/assistant/controller";
import { deferred, before, job, proposal, published, saved, harness } from "./support/background-writer";
import { assistantApi, conversation, jobsHarness, running, run } from "./support/background-jobs";

for (const phase of ["baseline", "submit"] as const) {
  test(`Stop fences a background send during ${phase}`, async () => {
    const h = jobsHarness(undefined, []), metadata = assistantApi(), reached = deferred<void>(), release = deferred<void>();
    const controller = new AssistantController(metadata.api, { sessionId: "session", apply: () => Promise.resolve() }, () => {}, 5000, h.jobs);
    try {
      await controller.init(); await h.jobs.refresh(); controller.draft("Keep background draft");
      if (phase === "submit") { const original = h.api.submit; h.api.submit = async request => { const value = await original(request); reached.resolve(); await release.promise; return value; }; }
      const sending = controller.send(async () => {
        if (phase === "baseline") { reached.resolve(); await release.promise; }
        return { response: before.response, scope: { kind: "resume" } };
      });
      await reached.promise; await controller.stop(); release.resolve(); await sending;
      assert.equal(h.calls.submit.length, phase === "submit" ? 1 : 0);
      assert.equal(h.calls.cancel, phase === "submit" ? 1 : 0);
      assert.equal(controller.view.draft, "Keep background draft");
      assert.equal(controller.view.pendingSend, false);
    } finally { release.resolve(); controller.close(); h.close(); }
  });
}

for (const [index, target] of ["other-project", job.submission.identity.projectId].entries()) {
  test(`NB-W10:v${index ? "06" : "04"} old project metadata cannot publish into ${index ? "a new instance" : "another project"}`, async () => {
    const old = jobsHarness(), next = jobsHarness(target), held = deferred<typeof old.state>(), reached = deferred<void>();
    old.projectReply(() => { reached.resolve(); return held.promise; });
    const seen: string[] = [], unsubscribe = old.jobs.subscribe(view => { if (view.project) seen.push(view.project.projectId); });
    try {
      await reached.promise; unsubscribe(); await next.jobs.refresh(); const current = structuredClone(next.jobs.view);
      held.resolve(old.state); await old.jobs.refresh();
      assert.deepEqual(next.jobs.view, current); assert.deepEqual(seen, []);
      assert.equal(old.calls.cancel, 0); assert.equal(next.calls.cancel, 0);
    } finally { held.resolve(old.state); unsubscribe(); old.close(); next.close(); }
  });
}

for (const [index, origin] of ["save", "receipt"].entries()) {
  test(`NB-W10:v${index ? "05" : "03"} an old editor ${origin} callback cannot replace the next visible buffer`, async () => {
    const old = harness(), next = harness(), reached = deferred<void>(), reply = deferred<{ schemaVersion: 1; job: typeof saved; view: typeof published }>();
    old.publishReply(() => { reached.resolve(); return reply.promise; });
    const work = old.writer.publish(job, proposal);
    try {
      await reached.promise; old.writer.close(); old.queue.close(); old.history.close();
      assert.ok(next.type("Visible input in the new editor")); const current = new Map(next.mounted);
      reply.resolve({ schemaVersion: 1, job: saved, view: published }); await assert.rejects(work, /WRITER_STALE_CALLBACK/u);
      assert.deepEqual(next.mounted, current); assert.equal(next.counts.notices, 0); assert.equal(old.counts.notices, 0);
      assert.equal(next.history.length, 1);
    } finally { reply.resolve({ schemaVersion: 1, job: saved, view: published }); await work.catch(() => {}); old.close(); next.close(); }
  });
}

test("screen-independent jobs keep their original accepted order and reject older snapshot cursors", async () => {
  const first = running("first", 1), second = running("second", 1), h = jobsHarness(undefined, [first, second]);
  try {
    await h.jobs.refresh(); h.set([{ ...first, eventCursor: 3 }, second]); await h.jobs.refresh();
    assert.deepEqual(h.jobs.view.project?.jobs.map(job => job.id), ["first", "second"]);
    h.set([first, second]); await h.jobs.refresh();
    assert.equal(h.jobs.view.project?.jobs[0]?.eventCursor, 3);
    const unsubscribe = h.jobs.subscribe(() => {}); unsubscribe(); assert.equal(h.timers.size, 1);
    assert.equal(h.calls.cancel, 0);
  } finally { h.close(); }
});

test("changing conversations and closing the assistant never stops a background job or opens a legacy lease", async () => {
  const h = jobsHarness(), metadata = assistantApi(), controller = new AssistantController(metadata.api,
    { sessionId: "assistant-session", apply: () => Promise.reject(new Error("Legacy publication reached")) }, () => {}, 5000, h.jobs);
  try {
    await h.jobs.refresh(); await controller.init(); assert.equal(controller.view.run?.id, "job-one");
    await controller.newConversation(); assert.equal(controller.view.conversationId, "conversation-two");
    await controller.select("conversation-one"); assert.equal(controller.view.run?.id, "job-one");
    controller.close(); assert.equal(h.timers.size, 1); assert.equal(h.calls.cancel, 0);
    assert.deepEqual(metadata.calls, { lease: 0, cancel: 0 });
  } finally { controller.close(); h.close(); }
});

test("a cached conversation projection for one job cannot regress another job's completed state", async () => {
  const first = running("first", 1), second = running("second", 1), h = jobsHarness(undefined, [first, second]);
  const metadata = assistantApi(), latest = deferred<void>();
  const controller = new AssistantController(metadata.api, { sessionId: "session", apply: () => Promise.resolve() }, view => {
    if (view.run?.id === "second" && view.run.state === "completed") latest.resolve();
  }, 5000, h.jobs);
  h.conversationReply(id => {
    const own = h.state.jobs.find(job => job.id === id); assert.ok(own);
    const value = conversation(own);
    return Promise.resolve({ ...value, runs: [run(first), run(second), run(own)].filter((value, index, all) => all.findIndex(item => item.id === value.id) === index)
      .map(value => value.id === own.id ? run(own) : value) });
  });
  try {
    await h.jobs.refresh(); await controller.init(); assert.equal(controller.view.run?.id, "second");
    h.set([first, { ...second, execution: "completed", eventCursor: 2 }]); await h.jobs.refresh(); await latest.promise;
    assert.equal(controller.view.run?.state, "completed"); assert.equal(h.calls.cancel, 0);
  } finally { controller.close(); h.close(); }
});

test("background Send retries keep the captured request and never acquire or stop a legacy owner", async () => {
  const h = jobsHarness(undefined, []), metadata = assistantApi(), controller = new AssistantController(metadata.api,
    { sessionId: "session", apply: () => Promise.reject(new Error("Legacy publication reached")) }, () => {}, 5000, h.jobs);
  const submit = h.api.submit; let first = true;
  h.api.submit = request => { if (first) { first = false; h.calls.submit.push(structuredClone(request)); return Promise.reject(new Error("Lost submit reply")); }
    return submit(request); };
  try {
    await controller.init(); controller.draft("Keep this background request");
    const baseline = () => Promise.resolve({ response: before.response, scope: { kind: "resume" as const } });
    await controller.send(baseline); assert.equal(controller.view.pendingSend, true);
    await controller.chooseModel("different-model"); await controller.send(baseline);
    assert.equal(h.calls.submit.length, 2); assert.deepEqual(h.calls.submit[0], h.calls.submit[1]);
    assert.deepEqual(metadata.calls, { lease: 0, cancel: 0 }); assert.equal(h.calls.cancel, 0);
  } finally { controller.close(); h.close(); }
});
