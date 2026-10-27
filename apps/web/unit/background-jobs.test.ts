import assert from "node:assert/strict";
import test from "node:test";
import { deferred, job, proposal, published, saved, harness } from "./support/background-writer";
import { jobsHarness, running } from "./support/background-jobs";

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
