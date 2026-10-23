import assert from "node:assert/strict";
import test from "node:test";
import { attachTemplateWriter } from "../src/background/connection";
import { TemplateBackgroundWriter } from "../src/background/template-writer";
import { WriterApi } from "../src/background/api";
import type { WriterViewV2 } from "../src/contracts/generated/background_writer_view_v2";
import type { WriterCaptureClipboardV2 } from "../src/contracts/generated/background_writer_capture_clipboard_v2";
import type { WriterMode } from "../src/background/writer-lifecycle";
import { jsonWireAt, type JsonWireNode } from "../src/contracts/lossless-json";
import { contentText, responseBlocks } from "../src/contracts/template-address";
import { DraftRepository, type LocalDraft } from "../src/background/drafts";
import { RichSaveQueue, snapshotIdentity, type TemplateAdoption } from "../src/rich/save-queue";
import { containerKey, type LocalContainer, type Side, type V7Intent } from "../src/rich/v7-translation";
import { client, harness, record, type Harness, type Traffic } from "./support/template-harness";

// Resume tokens use Web Storage; Node tests provide an isolated in-memory store.
function storage(): Storage {
  const values = new Map<string, string>();
  return { get length() { return values.size; }, clear: () => values.clear(), getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null, removeItem: key => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); } };
}
Object.assign(globalThis, { sessionStorage: storage(), localStorage: storage() });

const styles = { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" };
const paper: LocalContainer = { blockId: "block-paper-a", kind: "content", cellId: null };
function typing(offset: number, side: Side, text: string, prior: string): V7Intent {
  return { localId: `intent-${crypto.randomUUID()}`, prior: new Map([[containerKey(paper), prior]]),
    operation: { kind: "replace_text", container: paper, start: offset, end: offset, text, styles, side } };
}
function textOf(response: JsonWireNode): string {
  const content = responseBlocks(response).get("block-paper-a")?.groups[0]?.content;
  assert.ok(content); return contentText(content);
}

async function opened(value: Harness, traffic: Traffic[]) {
  const api = client(value, traffic), modes: WriterMode[] = [], locks: boolean[] = [], adopted: TemplateAdoption[] = [];
  let rows: LocalDraft[] = [];
  const repository = new DraftRepository({ transact: work => { const next = work(rows); rows = next.rows; return Promise.resolve(next.result); },
    discardProject: () => { rows = []; return Promise.resolve(); } }, () => Promise.reject(new Error("unused")));
  // The harness fixture holds an attached writer; it detaches cleanly so another session may open.
  const fixture = await api.templateRead(value.proof);
  await api.templateDetach({ schemaVersion: 2, proof: value.proof, canonicalRevision: fixture.writer.acknowledgedRevision,
    canonicalSha256: fixture.writer.acknowledgedSha256 ?? fixture.workspaceSha256, actionCursor: fixture.writer.acknowledgedCursor, touches: [] });
  const connection = await attachTemplateWriter(value.project, api, repository);
  assert.ok(connection?.proof, connection?.error ?? "attach failed");
  const writer = new TemplateBackgroundWriter(connection, { compositionEnd: () => Promise.resolve(),
    lock: locked => locks.push(locked), changed: mode => modes.push(mode) });
  const queue = new RichSaveQueue({ durable: writer.durable, sessionId: connection.proof.sessionId,
    ports: writer.queuePorts({ adopted: adoption => adopted.push(adoption), changed: () => {}, retained: () => {}, released: () => {} }) });
  writer.attach(queue);
  return { writer, queue, modes, locks, adopted };
}

test("V7 input advances null touches that the compact save acknowledges with the saved transaction", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], { writer, queue, adopted } = await opened(value, traffic);
    assert.equal(writer.mode, "normal");
    const start = textOf(writer.durable);
    writer.input(); queue.template.enqueue(typing(15, "before", "!", start), "action-1", 0);
    writer.input(); queue.template.enqueue(typing(16, "before", "?", "By Shared title! / Journal North."), "action-2", 0);
    await queue.flush();
    assert.equal(textOf(queue.template.durable), "By Shared title!? / Journal North.");
    const saves = traffic.filter(item => item.path.endsWith("/save")).map(item => record(JSON.parse(item.wire)));
    assert.equal(saves.length, 2);
    assert.deepEqual(saves[0]?.["touches"], [{ cursor: 1, mutation: null }, { cursor: 2, mutation: null }]);
    assert.equal(saves[0]?.["actionCursor"], 2);
    assert.deepEqual(saves[1]?.["touches"], [], "acknowledged touches are never resent with different bytes");
    assert.equal(writer.cursor, 2);
    assert.equal(adopted.length, 2);
  } finally { await value.close(); }
});

test("Undo and Redo drain input and run as server local-history commands that rebase the queue", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], { writer, queue, adopted } = await opened(value, traffic);
    const start = textOf(writer.durable);
    writer.input(); queue.template.enqueue(typing(15, "before", "!", start), "action-1", 0);
    await queue.flush();
    const ack = adopted[0]?.verification?.kind === "committed" ? adopted[0].verification.acknowledgment.localHistoryAck : null;
    assert.ok(ack); assert.equal(ack.actionId, "action-1");
    const undone = await writer.history("undo", "action-1", ack.generation);
    assert.equal(textOf(queue.template.durable), start);
    assert.ok(undone.localHistoryAck);
    await writer.history("redo", "action-1", undone.localHistoryAck.generation);
    assert.equal(textOf(queue.template.durable), "By Shared title! / Journal North.");
    // After the server history move, new input is expressed against the rebased state.
    writer.input(); queue.template.enqueue(typing(16, "before", "?", "By Shared title! / Journal North."), "action-2", 0);
    await queue.flush();
    assert.equal(textOf(queue.template.durable), "By Shared title!? / Journal North.");
    assert.equal(writer.mode, "normal");
  } finally { await value.close(); }
});

test("an unknown save outcome is resolved from the durable replay record before later input moves", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], { writer, queue } = await opened(value, traffic);
    const start = textOf(writer.durable);
    const api = writer.connection.api, save = api.templateSavePrepared.bind(api);
    let lose = true;
    // The first reply is lost after the server committed it.
    api.templateSavePrepared = async (...args) => {
      const result = await save(...args);
      if (lose) { lose = false; throw new Error("INVALID_RESULT"); }
      return result;
    };
    writer.input(); queue.template.enqueue(typing(15, "before", "!", start), "action-1", 0);
    writer.input(); queue.template.enqueue(typing(16, "before", "?", "By Shared title! / Journal North."), "action-2", 0);
    await assert.rejects(queue.flush(), /V7_OUTCOME_UNKNOWN/);
    await writer.recover();
    assert.equal(queue.template.state.kind, "ready");
    await queue.flush();
    assert.equal(textOf(queue.template.durable), "By Shared title!? / Journal North.");
    assert.equal(traffic.filter(item => item.path.endsWith("/save")).length, 2, "the committed head is not saved twice");
  } finally { await value.close(); }
});

test("navigation drains input, flushes touches and detaches cleanly", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], { writer, queue, locks } = await opened(value, traffic);
    writer.input(); queue.template.enqueue(typing(15, "before", "!", textOf(writer.durable)), "action-1", 0);
    await queue.flush();
    // Later input with no saved transaction yet: its touch must still be acknowledged before detaching.
    writer.input();
    await writer.navigate();
    assert.equal(writer.mode, "detached");
    assert.equal(textOf(queue.template.durable), "By Shared title! / Journal North.");
    const paths = traffic.map(item => item.path.split("/").at(-1));
    assert.deepEqual(paths.slice(-2), ["flush", "detach"]);
    assert.deepEqual(record(JSON.parse(traffic.at(-2)?.wire ?? "{}"))["touches"], [{ cursor: 2, mutation: null }]);
    assert.equal(locks.at(-1), true);
  } finally { await value.close(); }
});

test("one hundred unacknowledged touches lock input until the writer acknowledges them", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], { writer, locks } = await opened(value, traffic);
    for (let index = 0; index < 100; index++) writer.input();
    assert.equal(writer.writable, false); assert.equal(locks.at(-1), true);
    assert.throws(() => writer.input(), /WRITER_INPUT_BLOCKED/);
    await writer.flushTouches();
    assert.equal(writer.writable, true); assert.equal(locks.at(-1), false);
    assert.equal(record(jsonWireAt(writer.connection.viewWire, ["writer"]).value)["acknowledgedCursor"], 100);
  } finally { await value.close(); }
});

test("an older read cannot replace a newer saved and refreshed baseline", async () => {
  const value = await harness();
  try {
    const { writer, queue } = await opened(value, []), api = writer.connection.api, read = api.templateRead.bind(api);
    const old = await read(writer.proof);
    let deliver: (view: WriterViewV2) => void = () => {};
    const delayed = new Promise<WriterViewV2>(resolve => { deliver = resolve; });
    let first = true;
    api.templateRead = proof => { if (first) { first = false; return delayed; } return read(proof); };
    const stale = writer.refresh();
    writer.input(); queue.template.enqueue(typing(15, "before", "!", textOf(writer.durable)), "newer", 0);
    await queue.flush();
    assert.equal(await writer.refresh(), true);
    const latest = queue.template.durable.wire, connection = writer.connection.viewWire.wire;
    deliver(old);
    assert.equal(await stale, false);
    assert.equal(queue.template.durable.wire, latest);
    assert.equal(writer.connection.viewWire.wire, connection);
  } finally { await value.close(); }
});

test("a read that arrives after close cannot adopt a newer server revision", async () => {
  const value = await harness();
  try {
    const { writer, queue } = await opened(value, []), api = writer.connection.api;
    const before = queue.template.durable.wire, view = writer.connection.viewWire.wire;
    assert.equal((await fetch(value.origin + "/harness/advance", { method: "POST" })).ok, true);
    const newer = await api.templateRead(writer.proof);
    let deliver: (result: WriterViewV2) => void = () => {};
    api.templateRead = () => new Promise(resolve => { deliver = resolve; });
    const pending = writer.refresh();
    writer.close();
    deliver(newer);
    assert.equal(await pending, false);
    assert.equal(writer.mode, "closed");
    assert.equal(queue.template.durable.wire, before);
    assert.equal(writer.connection.viewWire.wire, view);
  } finally { await value.close(); }
});

for (const pending of [false, true]) test(`heartbeat recovery preserves known input without a fenced mutation (pending=${String(pending)})`, async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], { writer, queue } = await opened(value, traffic);
    if (pending) {
      writer.input(); queue.template.enqueue(typing(15, "before", "!", textOf(writer.durable)), "before-recovery", 0);
    }
    writer.connection.api.templateHeartbeat = () => Promise.reject(new TypeError("fetch failed"));
    await writer.heartbeat();
    assert.equal(writer.mode, "recovering"); assert.equal(queue.template.state.kind, "ready");
    await writer.recover();
    assert.equal(writer.mode, "normal");
    assert.equal(queue.template.pending.length, pending ? 1 : 0);
    if (!pending) {
      writer.input(); queue.template.enqueue(typing(15, "before", "!", textOf(writer.durable)), "after-recovery", 0);
    }
    await queue.flush();
    assert.equal(textOf(queue.template.durable), "By Shared title! / Journal North.");
    assert.equal(traffic.filter(item => item.path.endsWith("/save")).length, 1);
  } finally { await value.close(); }
});

test("a save retry keeps its header after later typing advances the cursor", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], { writer, queue } = await opened(value, traffic);
    const api = writer.connection.api, save = api.templateSavePrepared.bind(api);
    let lose = true;
    api.templateSavePrepared = async (...args) => {
      const result = await save(...args);
      if (lose) { lose = false; throw new TypeError("fetch failed"); }
      return result;
    };
    writer.input(); queue.template.enqueue(typing(15, "before", "!", textOf(writer.durable)), "first", 0);
    await assert.rejects(queue.flush(), /fetch failed/);
    writer.input(); queue.template.enqueue(typing(16, "before", "?", "By Shared title! / Journal North."), "second", 0);
    await queue.flush();
    const saves = traffic.filter(item => item.path.endsWith("/save"));
    assert.equal(saves.length, 3);
    assert.equal(saves[0]?.wire, saves[1]?.wire, "the committed head is retried with identical bytes");
    assert.equal(textOf(queue.template.durable), "By Shared title!? / Journal North.");
  } finally { await value.close(); }
});

test("clipboard replies must match the requested selection and snapshot", async () => {
  const value = await harness();
  try {
    const api = client(value, []), view = await api.templateRead(value.proof);
    const body: WriterCaptureClipboardV2 = { schemaVersion: 2, proof: value.proof, clientCaptureId: "capture-a",
      snapshot: snapshotIdentity(view.response.snapshot),
      selection: { kind: "blocks", blocks: [{ blockId: "block-paper-a", beforeRevision: 1 }] } };
    const captured = await api.templateCaptureClipboard(body);
    const delayed = new WriterApi(value.project, () => Promise.resolve(captured));
    assert.deepEqual(await delayed.templateCaptureClipboard(body), captured);
    await assert.rejects(delayed.templateCaptureClipboard({ ...body, clientCaptureId: "capture-b",
      selection: { kind: "blocks", blocks: [{ blockId: "block-paper-b", beforeRevision: 1 }] } }), /INVALID_RESULT/);
    const snapshot = snapshotIdentity({ ...body.snapshot, projectRevision: body.snapshot.projectRevision + 1 });
    await assert.rejects(delayed.templateCaptureClipboard({ ...body, snapshot }), /INVALID_RESULT/);
    const mutable = structuredClone(body);
    let deliver: (reply: unknown) => void = () => {};
    const held = new WriterApi(value.project, () => new Promise(resolve => { deliver = resolve; }));
    const pending = held.templateCaptureClipboard(mutable);
    mutable.selection = { kind: "blocks", blocks: [{ blockId: "block-paper-b", beforeRevision: 1 }] };
    mutable.snapshot = snapshot;
    deliver(captured);
    assert.deepEqual(await pending, captured, "later changes to the request object cannot change the captured identity");
  } finally { await value.close(); }
});
