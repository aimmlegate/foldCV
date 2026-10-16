import assert from "node:assert/strict";
import test from "node:test";
import { deferred, harness, job, proposal, published, saved } from "./support/background-writer";

const orders = [
  ["timeout", "input", "reply"], ["timeout", "reply", "input"], ["input", "timeout", "reply"],
  ["input", "reply", "timeout"], ["reply", "timeout", "input"], ["reply", "input", "timeout"],
] as const;
for (const order of orders) {
  test(`NB-M01:v02 timeout input late-reply order ${order.join("/")} preserves its independent oracle`, async () => {
    const h = harness(), reached = deferred<void>(), reply = deferred<{ schemaVersion: 1; job: typeof saved; view: typeof published }>();
    h.publishReply(() => { reached.resolve(); return reply.promise; });
    const work = h.writer.publish(job, proposal); void work.catch(() => {});
    let timedOut = false, delivered = false, accepted = false;
    try {
      await reached.promise;
      for (const action of order) {
        if (action === "timeout") {
          if (delivered) h.lateAlarm();
          else { h.expire(); await assert.rejects(work, /WRITER_BARRIER_TIMEOUT/u); timedOut = true; }
        } else if (action === "input") {
          const value = h.type("Input retained in this schedule");
          if (timedOut || delivered) { assert.ok(value); accepted = true; }
          else assert.equal(value, null);
        } else {
          reply.resolve({ schemaVersion: 1, job: saved, view: published });
          if (!timedOut) await work; else await h.settle();
          delivered = true;
        }
        assert.equal(h.counts.notices, delivered && !timedOut ? 1 : 0);
        assert.equal(h.writer.cursor, accepted ? 1 : 0);
        assert.equal(h.history.length, (delivered && !timedOut ? 1 : 0) + (accepted ? 1 : 0));
        if (accepted) {
          const value = h.cache.get(h.history.read("block:quote") ?? ""); assert.ok(value && Array.isArray(value.block.content));
          const span = value.block.content[0]; assert.ok(span && "text" in span); assert.equal(span.text, "Input retained in this schedule");
        }
      }
      if (accepted) { await h.writer.checkpoint(); assert.equal((await h.localDraft())?.record.cursor, 1); }
      assert.equal(h.counts.commits, 1); assert.equal(h.counts.saves, 0);
    } finally { reply.resolve({ schemaVersion: 1, job: saved, view: published }); await work.catch(() => {}); h.close(); }
  });
}
