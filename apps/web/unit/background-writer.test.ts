import assert from "node:assert/strict";
import test from "node:test";
import { deferred, harness, job, proposal, saved, published, offer } from "./support/background-writer";
import { RichApiFailure } from "../src/rich/api";
import type { CellChange, HistoryKind } from "../src/rich/history";

function injectedOrigin(h: ReturnType<typeof harness>, index: number): () => unknown {
  if (index <= 2) return () => h.type(index === 1 ? "Blocked typing" : "Pasted first line\nSecond line");
  if (index === 3) return () => h.history.undo();
  if (index === 4) return () => h.history.redo();
  let kind: HistoryKind = "structure", changes: CellChange[];
  if (index === 5) {
    const field = [...h.mounted].find(([key, value]) => key.startsWith("fact-field:") && value); assert.ok(field);
    const [key, before] = field, value: unknown = JSON.parse(before ?? "null");
    assert.ok(typeof value === "object" && value !== null && "rawText" in value);
    kind = "panel"; changes = [{ key, before, after: JSON.stringify({ ...value, rawText: "Blocked fact panel input" }) }];
  } else if (index === 6) {
    const table = [...h.mounted].map(([key, value]) => ({ key, value, stored: value ? h.cache.get(value) : null }))
      .find(item => item.stored?.block.type === "table"); assert.ok(table?.stored);
    const changed = structuredClone(table.stored); assert.equal(changed.block.type, "table");
    if (changed.block.type !== "table") throw new Error("Missing table");
    const cell = changed.block.content.rows[0]?.cells[0]; assert.ok(cell);
    cell.backgroundColor = "#ffeeaa";
    const after = JSON.stringify(changed); h.cache.set(after, changed);
    changes = [{ key: table.key, before: table.value, after }];
  } else if (index === 8) {
    const action = h.history.currentActionId; assert.ok(action);
    const capture = h.history.capture(action, ["block:quote"]), before = h.history.read("block:quote"); assert.ok(capture && before);
    const stored = h.cache.get(before); assert.ok(stored); const changed = structuredClone(stored);
    assert.ok(Array.isArray(changed.block.content)); const span = changed.block.content[0]; assert.ok(span && "text" in span);
    span.text = "Late synchronization result";
    const after = JSON.stringify(changed); h.cache.set(after, changed);
    return () => h.history.attach(capture, [{ key: "block:quote", before, after }]);
  } else {
    const key = "region:main", before = h.history.read(key); assert.ok(before);
    const ids: unknown = JSON.parse(before); assert.ok(Array.isArray(ids) && ids.every((id: unknown) => typeof id === "string"));
    if (index === 9) {
      assert.ok(ids.length > 1); changes = [{ key, before, after: JSON.stringify([...ids].reverse()) }];
    } else {
      const sample = [...h.cache.values()].find(item => item.block.type === "paragraph"); assert.ok(sample);
      const block = index === 7 ? { id: "completed-image", revision: 1, type: "image" as const, children: [], provenance: [], content: null,
        props: { assetId: "synthetic-pinned-image", alt: "Held image completion", caption: [], width: 100, height: 100, alignment: "left" as const } }
        : { ...structuredClone(sample.block), id: "completed-drop" };
      const stored = { block, children: [] }, after = JSON.stringify(stored); h.cache.set(after, stored);
      changes = [{ key: `block:${block.id}`, before: null, after }, { key, before, after: JSON.stringify([...ids, block.id]) }];
    }
  }
  return () => h.history.commit(kind, changes);
}

test("NB-H01:v01 mounted publication adopts one compiler result with one history action and no second save", async () => {
  const h = harness();
  try {
    await h.writer.publish(job, proposal); await h.writer.publish(job, proposal);
    assert.equal(h.history.length, 1); assert.equal(h.history.position, 1);
    assert.deepEqual(h.mounted, h.cells(published.response));
    assert.deepEqual(h.counts, { commits: 1, saves: 0, notices: 1, ownership: 1, history: 0, cancels: 0 });
    assert.ok(await h.writer.history("undo"));
    assert.equal(h.history.position, 0); assert.equal(h.counts.history, 1); assert.equal(h.counts.saves, 0);
  } finally { h.close(); }
});

test("NB-H01:v02 headless adoption adds the retained inverse without applying committed cells twice", async () => {
  const h = harness({ headless: true }), before = new Map(h.mounted);
  try {
    await h.writer.adoptHeadless(saved); await h.writer.adoptHeadless(saved);
    assert.deepEqual(h.mounted, before); assert.equal(h.history.length, 1); assert.equal(h.history.position, 1);
    assert.equal(h.counts.commits, 0); assert.equal(h.counts.saves, 0); assert.equal(h.counts.notices, 1);
  } finally { h.close(); }
});

test("NB-A04:v41 inverse expiry visibly intercepts Undo without falling back to a fresh local mutation", async () => {
  const h = harness();
  try {
    await h.writer.publish(job, proposal); const buffer = new Map(h.mounted), cursor = h.writer.cursor;
    h.writer.observeJob({ ...saved, undoExpired: true });
    assert.equal(await h.writer.history("undo"), true);
    assert.deepEqual(h.mounted, buffer); assert.equal(h.history.position, 1); assert.equal(h.writer.cursor, cursor);
    assert.equal(h.counts.history, 0); assert.equal(h.counts.saves, 0); assert.equal(h.counts.commits, 1);
    assert.equal(h.writer.mode, "normal"); assert.ok(h.errors.some(error => error.includes("Срок отмены этой правки истёк")));
    assert.ok(h.type("Independent input after inverse expiry"));
  } finally { h.close(); }
});

test("NB-W07:v04 a heartbeat reply from the previous connection cannot fence a resumed writer", async () => {
  const h = harness(), reached = deferred<void>(), reply = deferred<typeof h.writer.view>();
  const old = structuredClone(h.writer.view);
  h.api.heartbeat = () => { reached.resolve(); return reply.promise; };
  h.api.open = request => Promise.resolve({ ...old, writer: { ...old.writer, epoch: old.writer.epoch + 1, incarnation: request.incarnation } });
  const heartbeat = h.writer.heartbeat();
  try {
    await reached.promise; await h.writer.navigate(); await h.writer.resume();
    const current = h.writer.proof.incarnation; assert.notEqual(current, old.writer.incarnation);
    reply.resolve(old); await heartbeat;
    assert.equal(h.writer.mode, "normal"); assert.equal(h.writer.proof.incarnation, current); assert.equal(h.writer.writable, true);
    assert.equal(h.errors.length, 0);
  } finally { reply.resolve(old); await heartbeat; h.close(); }
});

test("a late local write from the old proof cannot advance the current writer's durable cursor", async () => {
  const h = harness(), reached = deferred<void>(), release = deferred<void>(), transact = h.database.transact.bind(h.database);
  h.database.transact = async work => { reached.resolve(); await release.promise; return transact(work); };
  try {
    assert.ok(h.type("Old writer input remains under its own key")); await reached.promise;
    const proof = { ...h.writer.proof, epoch: h.writer.proof.epoch + 1, incarnation: "next-connection" };
    h.connection.proof = proof;
    h.connection.view = { ...h.writer.view, writer: { ...h.writer.view.writer, epoch: proof.epoch, incarnation: proof.incarnation } };
    release.resolve();
    const write = h.database.transact; h.database.transact = transact;
    await write(rows => ({ rows, result: undefined })); await h.settle();
    assert.equal(h.writer.needsUnloadGuard, true);
    const record = await h.localDraft(); assert.ok(record); assert.notEqual(record.record.epoch, proof.epoch);
  } finally { release.resolve(); h.close(); }
});

for (let index = 1; index <= 10; index++) {
  const id = `NB-W03:v${String(index).padStart(2, "0")}`;
  test(`${id} shared transaction guard rejects a mutation between ACK and adoption`, async () => {
    const reached = deferred<void>(), release = deferred<void>();
    const h = harness({ observe: async name => { if (name === "barrier_acked") { reached.resolve(); await release.promise; } } });
    if (index === 3 || index === 4 || index === 8) {
      const project = h.queue.baseline.workspace.project; assert.ok(project);
      const quote = project.document.regions.flatMap(region => region.blocks.flatMap(block => [block, ...block.children])).find(block => block.id === "quote");
      assert.ok(quote && Array.isArray(quote.content)); const span = quote.content[0]; assert.ok(span && "text" in span);
      assert.ok(h.type("Undo setup"));
      if (index === 4) assert.ok(h.history.undo()); else assert.ok(h.type(span.text));
    }
    const inject = injectedOrigin(h, index);
    const task = h.writer.publish(job, proposal);
    try {
      await reached.promise; const before = new Map(h.mounted), cursor = h.writer.cursor;
      assert.ok(h.locked()); assert.equal(h.writer.writable, false);
      assert.equal(inject(), index === 3 || index === 4 ? false : index === 8 ? "conflict" : null);
      assert.deepEqual(h.mounted, before); assert.equal(h.writer.cursor, cursor);
      release.resolve(); await task; assert.equal(h.counts.notices, 1); assert.equal(h.history.length, index === 3 || index === 8 ? 3 : 1);
    } finally { release.resolve(); await task.catch(() => {}); h.close(); }
  });
}

for (const later of [false, true]) {
  test(`NB-W02:v${later ? "01" : "02"} a won commit and lost reply retain the timeout buffer until exact recovery`, async () => {
    const reply = deferred<{ schemaVersion: 1; job: typeof saved; view: typeof published }>(), committed = deferred<void>();
    const h = harness(); h.publishReply(() => { committed.resolve(); return reply.promise; });
    const task = h.writer.publish(job, proposal);
    try {
      await committed.promise; h.expire(); await assert.rejects(task, /WRITER_BARRIER_TIMEOUT/u);
      assert.equal(h.writer.mode, "recovering"); assert.equal(h.locked(), false);
      if (later) assert.ok(h.type("Input retained after timeout"));
      const buffer = new Map(h.mounted);
      reply.resolve({ schemaVersion: 1, job: saved, view: published }); await h.settle();
      assert.deepEqual(h.mounted, buffer); assert.equal(h.history.length, later ? 1 : 0); assert.equal(h.counts.notices, 0);
      await h.writer.recoverPublication(saved);
      if (later) {
        assert.equal(h.writer.mode, "recovering"); assert.deepEqual(h.mounted, buffer);
        await h.writer.checkpoint();
        const draft = await h.localDraft(); assert.ok(draft); assert.equal(draft.record.cursor, h.writer.cursor);
        assert.equal(h.counts.notices, 0);
      } else {
        assert.equal(h.writer.mode, "normal"); assert.deepEqual(h.mounted, h.cells(offer.view.response));
        assert.equal(h.history.length, 1); assert.equal(h.counts.notices, 1);
      }
      assert.equal(h.counts.commits, 1); assert.equal(h.counts.saves, 0);
    } finally { reply.resolve({ schemaVersion: 1, job: saved, view: published }); await task.catch(() => {}); h.close(); }
  });
}

test("timeout after history reservation releases local input while the stale adoption callback remains blocked", async () => {
  const reached = deferred<void>(), release = deferred<void>();
  const h = harness({ observe: async name => { if (name === "adoption_started") { reached.resolve(); await release.promise; } } });
  const task = h.writer.publish(job, proposal);
  try {
    await reached.promise; h.expire(); await assert.rejects(task, /WRITER_BARRIER_TIMEOUT/u);
    assert.ok(h.type("Input after adoption timeout")); const retained = new Map(h.mounted);
    release.resolve(); await h.settle(); await h.writer.checkpoint();
    assert.deepEqual(h.mounted, retained); assert.equal(h.counts.notices, 0); assert.equal(h.history.length, 1);
    assert.equal(h.counts.commits, 1); assert.equal(h.counts.saves, 0);
  } finally { release.resolve(); await task.catch(() => {}); h.close(); }
});

test("an ineligible old headless inverse keeps the current editor usable and creates no new saved notice", async () => {
  const h = harness({ headless: true }), mounted = new Map(h.mounted);
  h.offerReply(() => Promise.reject(new RichApiFailure("DEPENDENCY_CHANGED", 409)));
  try {
    await h.writer.adoptHeadless(saved);
    assert.equal(h.writer.mode, "normal"); assert.equal(h.locked(), false); assert.equal(h.history.length, 0);
    assert.equal(h.counts.notices, 0); assert.deepEqual(h.mounted, mounted);
  } finally { h.close(); }
});

test("NB-W02:v03 failed exact recovery keeps the local buffer and emits no saved notice", async () => {
  const reached = deferred<void>(), reply = deferred<{ schemaVersion: 1; job: typeof saved; view: typeof published }>();
  const h = harness(); h.publishReply(() => { reached.resolve(); return reply.promise; });
  const task = h.writer.publish(job, proposal);
  try {
    await reached.promise; h.expire(); await assert.rejects(task, /WRITER_BARRIER_TIMEOUT/u);
    await h.writer.checkpoint(); const buffer = new Map(h.mounted); let reads = 0;
    h.readReply(() => { reads++; return Promise.reject(new Error("Exact recovery unavailable")); });
    await assert.rejects(h.writer.recoverPublication(saved), /Exact recovery unavailable/u); assert.equal(reads, 1);
    reply.resolve({ schemaVersion: 1, job: saved, view: published }); await h.settle();
    assert.equal(h.writer.mode, "recovering"); assert.deepEqual(h.mounted, buffer);
    assert.equal(h.counts.notices, 0); assert.equal(h.counts.ownership, 0); assert.equal(h.counts.saves, 0);
  } finally { reply.resolve({ schemaVersion: 1, job: saved, view: published }); await task.catch(() => {}); h.close(); }
});

test("exact recovery waits for a checkpoint still persisting its local payload before server delivery", async () => {
  const reached = deferred<void>(), release = deferred<void>();
  const h = harness(), reply = deferred<{ schemaVersion: 1; job: typeof saved; view: typeof published }>();
  h.publishReply(() => { reached.resolve(); return reply.promise; });
  const task = h.writer.publish(job, proposal);
  try {
    await reached.promise;
    const transact = h.database.transact.bind(h.database);
    h.database.transact = async work => { await release.promise; return transact(work); };
    h.expire(); await assert.rejects(task, /WRITER_BARRIER_TIMEOUT/u);
    let reads = 0;
    h.readReply(() => { reads++; return Promise.resolve(structuredClone(offer.view)); });
    const recovery = h.writer.recoverPublication(saved);
    await h.settle(); assert.equal(reads, 0); assert.equal(h.counts.notices, 0);
    release.resolve(); await recovery;
    assert.equal(reads, 2); assert.equal(h.writer.mode, "normal"); assert.equal(h.counts.notices, 1);
    reply.resolve({ schemaVersion: 1, job: saved, view: published }); await h.settle();
    assert.equal(h.counts.notices, 1);
  } finally { release.resolve(); reply.resolve({ schemaVersion: 1, job: saved, view: published }); await task.catch(() => {}); h.close(); }
});

for (const [index, order] of ["event-first", "reply-first", "duplicates"].entries()) {
  test(`NB-W02:v${String(index + 4).padStart(2, "0")} ${order} delivery creates one adoption and notice`, async () => {
    const reached = deferred<void>(), reply = deferred<{ schemaVersion: 1; job: typeof saved; view: typeof published }>();
    const h = harness(); h.publishReply(() => { reached.resolve(); return reply.promise; });
    const task = h.writer.publish(job, proposal);
    let event: Promise<void> | null = null;
    try {
      await reached.promise;
      if (order === "event-first" || order === "duplicates") event = h.writer.adoptHeadless(saved);
      if (order === "duplicates") void h.writer.publish(job, proposal);
      assert.equal(h.counts.notices, 0); reply.resolve({ schemaVersion: 1, job: saved, view: published });
      await task; await event; await h.writer.adoptHeadless(saved); await h.writer.publish(job, proposal);
      assert.equal(h.counts.commits, 1); assert.equal(h.counts.notices, 1); assert.equal(h.counts.ownership, 1);
      assert.equal(h.history.length, 1); assert.equal(h.counts.saves, 0); assert.deepEqual(h.mounted, h.cells(published.response));
    } finally { reply.resolve({ schemaVersion: 1, job: saved, view: published }); await task.catch(() => {}); await event?.catch(() => {}); h.close(); }
  });
}

for (const [index, cut] of ["composition", "flush", "continuous-input", "budget"].entries()) {
  test(`NB-W04:v${String(index + 1).padStart(2, "0")} ${cut} respects composition and the bounded local window`, async () => {
    const entered = deferred<void>(), release = deferred<void>(), composition = deferred<void>();
    const h = harness({ observe: async name => {
      if (cut !== "composition" && name === "final_flush_started") { entered.resolve(); await release.promise; }
    } });
    h.composition(composition.promise);
    const task = h.writer.publish(job, proposal);
    try {
      await h.settle(); assert.equal(h.locked(), false); assert.equal(h.counts.commits, 0);
      assert.ok(!h.hooks.includes("final_flush_started"));
      composition.resolve();
      if (cut === "composition") { await task; assert.equal(h.counts.notices, 1); }
      else {
        await entered.promise; assert.ok(h.locked());
        if (cut === "flush") { release.resolve(); await task; assert.equal(h.counts.notices, 1); }
        else {
          h.expire(); await assert.rejects(task, /WRITER_BARRIER_TIMEOUT/u);
          if (cut === "continuous-input") {
            assert.ok(h.type("First retained input")); assert.ok(h.type("Second retained input")); await h.writer.checkpoint();
            assert.equal((await h.localDraft())?.record.cursor, 2);
          }
          release.resolve(); await h.settle(); assert.equal(h.counts.notices, 0); assert.equal(h.counts.commits, 0);
          assert.equal(h.writer.mode, "recovering"); assert.equal(h.locked(), false);
        }
      }
    } finally { composition.resolve(); release.resolve(); await task.catch(() => {}); h.close(); }
  });
}

test("continuous zero-diff input flushes before its bounded touch queue can silently drop more typing", async () => {
  const h = harness(), reached = deferred<void>(), release = deferred<void>(), flush = h.api.flush;
  h.api.flush = async request => { reached.resolve(); await release.promise; return flush(request); };
  try {
    for (let index = 0; index < 50; index++) { assert.ok(h.type(`Transient ${String(index)}`)); assert.ok(h.history.undo()); }
    assert.equal(h.writer.cursor, 100); assert.equal(h.writer.writable, false); assert.ok(h.locked());
    assert.ok(h.errors.some(error => error.includes("Дождитесь сохранения")));
    const before = new Map(h.mounted); assert.equal(h.type("Held until flush"), null); assert.deepEqual(h.mounted, before);
    await reached.promise; release.resolve(); await h.writer.flushTouches();
    assert.equal(h.writer.writable, true); assert.equal(h.locked(), false); assert.equal(h.writer.cursor, 100);
    assert.ok(h.type("Input after the durable watermark")); await h.writer.checkpoint();
    assert.equal(h.writer.cursor, 101); assert.equal(h.counts.saves, 0); assert.equal(h.counts.commits, 0);
  } finally { release.resolve(); h.close(); }
});

test("a clean writer needs no unload prompt while its dirty durable draft still retains image ownership", async () => {
  const h = harness();
  try {
    assert.equal(h.writer.needsUnloadGuard, false); assert.equal(h.writer.retainsDraft, false);
    assert.ok(h.type("Durable local input")); assert.equal(h.writer.needsUnloadGuard, true);
    await h.writer.checkpoint();
    assert.equal(h.writer.needsUnloadGuard, false); assert.equal(h.writer.retainsDraft, true);
    assert.equal(h.counts.saves, 0); assert.equal(h.counts.notices, 0);
  } finally { h.close(); }
});

for (const [index, code] of ["SAVE_FAILED", "OUTCOME_UNKNOWN", "WRITER_UNKNOWN"].entries()) {
  test(`NB-W05:v${String(index + 2).padStart(2, "0")} ${code} navigation keeps a durable local checkpoint`, async () => {
    const h = harness();
    if (code === "WRITER_UNKNOWN") {
      assert.ok(h.type("Touched then undone")); assert.ok(h.history.undo());
      h.api.flush = () => Promise.reject(new RichApiFailure(code, 409));
    } else {
      assert.ok(h.type("Input stays available after the save failure"));
      h.api.save = () => { h.counts.saves++; return Promise.reject(new RichApiFailure(code, 409)); };
    }
    h.api.checkpoint = () => Promise.reject(new Error("Server checkpoint unavailable"));
    const buffer = new Map(h.mounted);
    try {
      await h.writer.navigate();
      assert.equal(h.writer.mode, "recovering"); assert.deepEqual(h.mounted, buffer);
      const draft = await h.localDraft(); assert.ok(draft); assert.equal(draft.record.cursor, h.writer.cursor);
      assert.equal(h.writer.needsUnloadGuard, false); assert.equal(h.counts.notices, 0); assert.equal(h.counts.commits, 0);
      if (code === "WRITER_UNKNOWN") assert.equal(draft.payload.touches?.length, 2);
    } finally { h.close(); }
  });
}

test("NB-W05:v05 a lost detach ACK cannot unlock an old canonical save or replace later recovery input", async () => {
  const h = harness(), reached = deferred<void>(), reply = deferred<Awaited<ReturnType<typeof h.api.detach>>>(), detach = h.api.detach;
  h.api.detach = async request => { const saved = await detach(request); reached.resolve(); await reply.promise; return saved; };
  const navigation = h.writer.navigate();
  try {
    await reached.promise; h.expire(); await navigation;
    assert.equal(h.writer.mode, "recovering"); assert.ok(h.type("Local input after a lost detach ACK"));
    const buffer = new Map(h.mounted); reply.resolve(await detach({ schemaVersion: 1, proof: h.writer.proof,
      canonicalRevision: h.writer.view.response.workspace.projectRevision, canonicalSha256: h.writer.view.workspaceSha256, actionCursor: 0, touches: [] }));
    await h.settle(); await h.writer.checkpoint();
    assert.deepEqual(h.mounted, buffer); assert.equal(h.writer.mode, "recovering"); assert.equal(h.counts.saves, 0);
    assert.equal((await h.localDraft())?.record.cursor, 1);
  } finally { reply.resolve(h.writer.view); await navigation.catch(() => {}); h.close(); }
});

test("NB-W05:v06 input after the final touch flush cannot enter the protected detach boundary", async () => {
  const reached = deferred<void>(), release = deferred<void>();
  const h = harness({ observe: async name => { if (name === "touch_watermark_durable") { reached.resolve(); await release.promise; } } });
  const navigation = h.writer.navigate();
  try {
    await reached.promise; const buffer = new Map(h.mounted);
    assert.equal(h.type("Blocked after the final flush"), null); assert.deepEqual(h.mounted, buffer);
    release.resolve(); await navigation;
    assert.equal(h.writer.mode, "detached"); assert.equal(h.writer.cursor, 0); assert.equal(h.counts.notices, 0);
  } finally { release.resolve(); await navigation.catch(() => {}); h.close(); }
});
