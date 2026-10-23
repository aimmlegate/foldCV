import assert from "node:assert/strict";
import test from "node:test";
import type { WriterApi } from "../src/background/api";
import type { WriterPrepareEditV2 } from "../src/contracts/generated/background_writer_prepare_edit_v2";
import { jsonObjectWire, jsonWireAt, parseJsonWire, type JsonWireNode } from "../src/contracts/lossless-json";
import { contentText, responseBlocks } from "../src/contracts/template-address";
import type { PreparedSaveOpening, TemplateSaveVerification } from "../src/contracts/template-save";
import { RichApiFailure } from "../src/rich/api";
import { RichSaveQueue, type TemplateAdoption, type TemplateQueueState } from "../src/rich/save-queue";
import { containerKey, correctionRange, type LocalContainer, type Side, type V7Intent } from "../src/rich/v7-translation";
import { bootstrap, client, harness, meter, number, record, string, type Harness, type Traffic } from "./support/template-harness";

type Events = { adopted: TemplateAdoption[]; states: TemplateQueueState[]; retained: string[]; released: string[] };
function events(): Events { return { adopted: [], states: [], retained: [], released: [] }; }

/** The writer port this slice needs: a V2 header from the latest acknowledged writer state. */
function queue(value: Harness, api: WriterApi, view: JsonWireNode, seen: Events,
  save: (run: () => Promise<TemplateSaveVerification>) => Promise<TemplateSaveVerification> = run => run()): RichSaveQueue {
  const writer = record(jsonWireAt(view, ["writer"]).value);
  let acknowledged = { revision: number(writer["acknowledgedRevision"]), sha256: string(writer["acknowledgedSha256"]),
    cursor: number(writer["acknowledgedCursor"]), touchGeneration: number(writer["touchGeneration"]) };
  const opening = (): PreparedSaveOpening => ({ projectId: value.project, lineage: value.proof.lineage, epoch: value.proof.epoch,
    sessionId: value.proof.sessionId, incarnation: value.proof.incarnation, actionCursor: acknowledged.cursor,
    minimumTouchGeneration: acknowledged.touchGeneration });
  return new RichSaveQueue({ durable: jsonWireAt(view, ["response"]), sessionId: value.proof.sessionId, ports: {
    proof: () => value.proof,
    prepare: (base: JsonWireNode, request: WriterPrepareEditV2) => api.templatePrepareDelta(base, request),
    save: preparation => save(async () => {
      const header = parseJsonWire(jsonObjectWire([["schemaVersion", "2"], ["proof", JSON.stringify(value.proof)],
        ["canonicalRevision", String(acknowledged.revision)], ["canonicalSha256", JSON.stringify(acknowledged.sha256)],
        ["actionCursor", String(acknowledged.cursor)], ["touches", "[]"]]));
      const result = await api.templateSavePrepared(header, preparation, opening());
      const session = result.acknowledgment.writer;
      acknowledged = { revision: session.acknowledgedRevision, sha256: session.acknowledgedSha256 ?? acknowledged.sha256,
        cursor: session.acknowledgedCursor, touchGeneration: session.touchGeneration };
      return result;
    }),
    adopted: adoption => seen.adopted.push(adoption),
    changed: state => seen.states.push(state),
    retained: actionId => seen.retained.push(actionId),
    released: actionId => seen.released.push(actionId),
  } });
}

const styles = { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" };
const paper: LocalContainer = { blockId: "block-paper-a", kind: "content", cellId: null };
function typing(container: LocalContainer, offset: number, side: Side, text: string, prior: string): V7Intent {
  return { localId: `intent-${crypto.randomUUID()}`, prior: new Map([[containerKey(container), prior]]),
    operation: { kind: "replace_text", container, start: offset, end: offset, text, styles, side } };
}
function textOf(response: JsonWireNode, id: string): string {
  const content = responseBlocks(response).get(id)?.groups[0]?.content;
  assert.ok(content); return contentText(content);
}
function prepares(traffic: Traffic[]): Traffic[] { return traffic.filter(item => item.path.endsWith("/prepare-delta")); }
function saves(traffic: Traffic[]): Traffic[] { return traffic.filter(item => item.path.endsWith("/save")); }

test("buffered typing after a pending field edit is translated through each verified result and saved in order", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], seen = events();
    const view = await bootstrap(value), subject = queue(value, client(value, traffic), view, seen), v7 = subject.template;
    const start = textOf(jsonWireAt(view, ["response"]), "block-paper-a");
    assert.equal(start, "By Shared title / Journal North.");
    v7.enqueue(typing(paper, 8, "interior", "X", start), "action-1", 0);
    const first = subject.flush();
    // Typed while the head is in flight: expressed against the optimistic text, issued only after its result.
    v7.enqueue(typing(paper, 9, "before", "Y", "By ShareXd title / Journal North."), "action-2", 0);
    v7.enqueue(typing(paper, 10, "before", "Z", "By ShareXYd title / Journal North."), "action-2", 1);
    meter.peak = 0;
    const second = subject.flush();
    await first; await second;
    assert.equal(meter.peak, 1, "one in-flight request per scheduler, even with overlapping flush calls");
    assert.equal(textOf(v7.durable, "block-paper-a"), "By ShareXYZd title / Journal North.");
    assert.equal(prepares(traffic).length, 2, "contiguous typing in one action is one prepared transaction");
    assert.equal(saves(traffic).length, 2);
    const sent = record(JSON.parse(prepares(traffic)[1]?.wire ?? "{}"));
    const operations = record(sent["preparation"])["operations"];
    assert.ok(Array.isArray(operations));
    const operation = record(operations[0]);
    assert.equal(operation["text"], "YZ");
    const target = record(record(operation["range"])["insertionTarget"]);
    assert.equal(target["kind"], "field");
    assert.notEqual(target["bindingId"], "fragment-paper-a", "the inserted piece has a new server identity");
    assert.deepEqual(seen.adopted.map(item => item.noOp), [false, false]);
    assert.deepEqual(seen.retained, ["action-1", "action-2"]);
    assert.equal(v7.state.kind, "ready");
  } finally { await value.close(); }
});

test("typing in two different actions is never coalesced", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [];
    const view = await bootstrap(value), subject = queue(value, client(value, traffic), view, events());
    subject.template.enqueue(typing(paper, 15, "before", "a", "By Shared title / Journal North."), "action-1", 0);
    subject.template.enqueue(typing(paper, 16, "before", "b", "By Shared titlea / Journal North."), "action-2", 0);
    await subject.flush();
    assert.equal(prepares(traffic).length, 2);
    assert.equal(textOf(subject.template.durable, "block-paper-a"), "By Shared titleab / Journal North.");
  } finally { await value.close(); }
});

test("lost prepare and save replies resend identical frozen bytes and adopt the server's single result", async () => {
  for (const path of ["/prepare-delta", "/save"]) {
    const value = await harness();
    try {
      const traffic: Traffic[] = [], seen = events();
      const view = await bootstrap(value), subject = queue(value, client(value, traffic, { path, times: 1 }), view, seen);
      subject.template.enqueue(typing(paper, 15, "after", "!", "By Shared title / Journal North."), "action-1", 0);
      await assert.rejects(subject.flush(), /fetch failed/);
      assert.equal(subject.template.state.kind, "ready");
      assert.equal(subject.template.pending[0]?.stage, path === "/save" ? "prepared" : "frozen");
      await subject.flush();
      const sent = traffic.filter(item => item.path.endsWith(path));
      assert.equal(sent.length, 2); assert.equal(sent[0]?.wire, sent[1]?.wire, path);
      assert.equal(textOf(subject.template.durable, "block-paper-a"), "By Shared title! / Journal North.");
      assert.equal(seen.adopted.length, 1);
    } finally { await value.close(); }
  }
});

test("a no-op preparation adopts nothing, sends no save and releases only a sealed empty action", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], seen = events();
    const view = await bootstrap(value), subject = queue(value, client(value, traffic), view, seen), v7 = subject.template;
    const start = textOf(jsonWireAt(view, ["response"]), "block-paper-a");
    const same: V7Intent = { localId: "same", prior: new Map([[containerKey(paper), start]]), operation: { kind: "replace_text",
      container: paper, start: 3, end: 15, text: "Shared title", styles, side: null } };
    v7.enqueue(same, "action-mixed", 0);
    // Not contiguous with the no-op range, so it stays a separate intent of the same action.
    v7.enqueue(typing(paper, 32, "before", "!", start), "action-mixed", 1);
    v7.enqueue({ ...same, localId: "same-2", prior: new Map([[containerKey(paper), "By Shared title / Journal North.!"]]) }, "action-empty", 0);
    await subject.flush();
    assert.deepEqual(seen.adopted.map(item => item.noOp), [true, false, true]);
    assert.equal(saves(traffic).length, 1);
    v7.seal("action-mixed");
    assert.deepEqual(seen.released, [], "a no-op inside a committed action does not release it");
    assert.deepEqual(seen.retained, ["action-mixed"]);
    assert.deepEqual(seen.released, []);
    v7.seal("action-empty");
    assert.deepEqual(seen.released, ["action-empty"]);
  } finally { await value.close(); }
});

test("a translation conflict keeps every buffered intent, sends nothing and recovers by correction", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], seen = events();
    const view = await bootstrap(value), subject = queue(value, client(value, traffic), view, seen), v7 = subject.template;
    const canonical = textOf(jsonWireAt(view, ["response"]), "block-paper-a");
    v7.enqueue(typing(paper, 9, "before", "Y", "text the server never had"), "action-1", 0);
    v7.enqueue(typing(paper, 10, "before", "Z", "later"), "action-2", 0);
    await assert.rejects(subject.flush(), /V7_INPUT_CONFLICT/);
    assert.equal(v7.state.kind, "conflict"); assert.equal(v7.pending.length, 2);
    assert.equal(prepares(traffic).length, 0);
    await assert.rejects(subject.flush(), /V7_INPUT_CONFLICT/);
    // The editor holds its own text; correction re-expresses it against the canonical state.
    const editor = "By Shared title / Journal North. More";
    const range = correctionRange(canonical, editor);
    assert.deepEqual(range, { start: 32, end: 32, text: " More" });
    if (!range) return;
    const fix: V7Intent = { localId: "fix", prior: new Map([[containerKey(paper), canonical]]), operation: { kind: "replace_text",
      container: paper, ...range, styles, side: "after" } };
    // The pending input began from text the saved state never had: only an explicit keep choice may replace it.
    assert.throws(() => v7.correct([fix], "action-fix", 0), /V7_CORRECTION_CONFLICT/);
    assert.equal(v7.pending.length, 2);
    v7.correct([fix], "action-fix", 0, { keepEditorText: new Set([containerKey(paper)]) });
    v7.seal("action-1"); v7.seal("action-2");
    assert.deepEqual(seen.released, ["action-1", "action-2"]);
    await subject.flush();
    assert.equal(textOf(v7.durable, "block-paper-a"), editor);
    assert.deepEqual(seen.retained, ["action-fix"]);
  } finally { await value.close(); }
});

test("a definitive server rejection keeps the rejected head and later input, sends no save and allows correction", async () => {
  const value = await harness("linked");
  try {
    const traffic: Traffic[] = [], seen = events();
    const view = await bootstrap(value), subject = queue(value, client(value, traffic), view, seen), v7 = subject.template;
    const start = textOf(jsonWireAt(view, ["response"]), "block-paper-a");
    assert.equal(start, "See example page now");
    // Literal input strictly inside plain link text has no supported address; Python decides that, not the client.
    v7.enqueue(typing(paper, 6, "interior", "x", start), "action-1", 0);
    v7.enqueue(typing(paper, 7, "before", "y", "See exxample page now"), "action-1", 1);
    v7.enqueue(typing(paper, 20, "after", "!", "See exxyample page now"), "action-2", 0);
    await assert.rejects(subject.flush(), /V7_INPUT_REJECTED/);
    assert.deepEqual(v7.state, { kind: "rejected", reason: "JOB_SCOPE_INVALID" });
    assert.equal(v7.pending.length, 2, "the rejected head (coalesced) and later input remain");
    assert.equal(prepares(traffic).length, 1); assert.equal(saves(traffic).length, 0);
    await assert.rejects(subject.flush(), /V7_INPUT_REJECTED/);
    assert.equal(prepares(traffic).length, 1, "a rejected head is not resent");
    assert.equal(v7.durable.wire, jsonWireAt(view, ["response"]).wire);
    // The user moves the typed text out of the link; the corrected input saves normally.
    const editor = "See example page now!", range = correctionRange(start, editor);
    assert.ok(range);
    assert.deepEqual(v7.unsavedBase().get(containerKey(paper)), start);
    // Input in another container must not vanish because the correction omitted it.
    const other: LocalContainer = { blockId: "block-paper-b", kind: "content", cellId: null };
    v7.enqueue(typing(other, 0, "after", "Q", "Shared title"), "action-3", 0);
    const fix: V7Intent = { localId: "fix", prior: new Map([[containerKey(paper), start]]), operation: { kind: "replace_text",
      container: paper, ...range, styles, side: "before" } };
    assert.throws(() => v7.correct([fix], "action-fix", 0), /V7_CORRECTION_NOT_ALLOWED/);
    assert.equal(v7.pending.length, 3);
    v7.correct([fix], "action-fix", 0, { unchanged: new Set([containerKey(other)]) });
    await subject.flush();
    assert.equal(textOf(v7.durable, "block-paper-a"), editor);
  } finally { await value.close(); }
});

test("an unknown save outcome fences dispatch, refuses discard and resumes only after recovery resolves the head", async () => {
  for (const committed of [true, false]) {
    const value = await harness();
    try {
      const traffic: Traffic[] = [], seen = events();
      let mode: "lose-after-commit" | "unknown-before-commit" | "normal" = committed ? "lose-after-commit" : "unknown-before-commit";
      const view = await bootstrap(value), api = client(value, traffic);
      const subject = queue(value, api, view, seen, async run => {
        if (mode === "unknown-before-commit") { mode = "normal"; throw new RichApiFailure("WRITER_UNKNOWN", 409); }
        const result = await run();
        if (mode === "lose-after-commit") { mode = "normal"; throw new Error("INVALID_RESULT"); }
        return result;
      }), v7 = subject.template;
      const start = textOf(jsonWireAt(view, ["response"]), "block-paper-a");
      v7.enqueue(typing(paper, 8, "interior", "X", start), "action-1", 0);
      v7.enqueue(typing(paper, 9, "before", "Y", "By ShareXd title / Journal North."), "action-2", 0);
      await assert.rejects(subject.flush(), /V7_OUTCOME_UNKNOWN/);
      assert.equal(v7.state.kind, "fenced");
      assert.throws(() => v7.discardUnsaved(), /восстановления/);
      await assert.rejects(subject.flush(), /V7_OUTCOME_UNKNOWN/);
      // Writer recovery: read the durable state and decide from the server's own replay record.
      const read = jsonWireAt(await bootstrap(value), ["response"]);
      const replay = jsonWireAt(read, ["workspace", "mutationReplay"]).value;
      assert.ok(Array.isArray(replay));
      const head = v7.pending[0]?.clientMutationId;
      const found = replay.some((item: unknown) => record(item)["clientMutationId"] === head);
      assert.equal(found, committed);
      subject.resolveTemplateOutcome(read, found);
      assert.equal(v7.state.kind, "ready");
      await subject.flush();
      assert.equal(textOf(v7.durable, "block-paper-a"), "By ShareXYd title / Journal North.");
      assert.equal(saves(traffic).length, 2, "the unknown head was sent at most once more, then the next intent");
    } finally { await value.close(); }
  }
});

test("typing into the local block created by a pending split resolves through its created entry", async () => {
  const value = await harness();
  try {
    const traffic: Traffic[] = [], seen = events();
    const view = await bootstrap(value), subject = queue(value, client(value, traffic), view, seen), v7 = subject.template;
    const start = textOf(jsonWireAt(view, ["response"]), "block-paper-a");
    const local: LocalContainer = { blockId: "local-right", kind: "content", cellId: null };
    v7.enqueue({ localId: "split", prior: new Map([[containerKey(paper), start]]),
      operation: { kind: "split_block", container: paper, offset: 8, created: "local-right" } }, "action-1", 0);
    v7.enqueue(typing(local, 0, "after", "Q", "d title / Journal North."), "action-2", 0);
    v7.enqueue(typing(paper, 8, "before", "!", "By Share"), "action-3", 0);
    await subject.flush();
    const right = v7.localBlocks.get("local-right");
    assert.ok(right);
    assert.equal(textOf(v7.durable, right), "Qd title / Journal North.");
    assert.equal(textOf(v7.durable, "block-paper-a"), "By Share!");
    assert.equal(seen.adopted.length, 3);
  } finally { await value.close(); }
});

test("the V1 constructor keeps document-diff queues and rejects V7 calls", () => {
  assert.throws(() => new RichSaveQueue({ durable: parseJsonWire("{}"), sessionId: "s", ports: {
    proof: () => { throw new Error("unused"); }, prepare: () => Promise.reject(new Error("unused")), save: () => Promise.reject(new Error("unused")),
    adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {} } }).baseline, /V1_QUEUE_REQUIRED/);
});
