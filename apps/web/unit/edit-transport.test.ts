import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { RichSaveQueue, type TemplateQueuedIntent } from "../src/rich/save-queue";
import { ProjectApiFailure, ProjectEditorConnection, type EditResult, type Fetcher } from "../src/rich/v7-connection";
import { containerKey, type V7Intent } from "../src/rich/v7-translation";

const base = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/projects/v7-response.json", import.meta.url), "utf8")) as TemplateProjectResponseV1;
const container = { blockId: "block-paper-a", kind: "content" as const, cellId: null };
const intent: V7Intent = { localId: "op", prior: new Map([[containerKey(container), "By Shared title / Journal North."]]),
  operation: { kind: "replace_text", container, start: 8, end: 8, text: "X", side: "interior",
    styles: { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" } } };
function result(response: TemplateProjectResponseV1, id: string): EditResult {
  return { schemaVersion: 1, revision: response.workspace.projectRevision, documentRevision: response.workspace.documentRevision,
    clientMutationId: id, replayed: false, response, createdIds: {}, createdBlocks: {}, changedBlockIds: [], history: { undo: null, redo: null } };
}

test("one intent makes one editing request and adopts the full response", async () => {
  const sent: string[] = [], response = structuredClone(base);
  response.workspace.projectRevision++;
  const queue = new RichSaveQueue({ durable: base, sessionId: "session", ports: {
    edit: request => { sent.push(request.clientMutationId); return Promise.resolve(result(response, request.clientMutationId)); },
    read: () => Promise.resolve(response), adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {}, lost: () => assert.fail("lost"),
  } });
  queue.template.enqueue(intent, "action", 0, "mutation");
  await queue.flush();
  assert.deepEqual(sent, ["mutation"]);
  assert.equal(queue.template.durable, response);
  assert.equal(queue.template.pending.length, 0);
});

test("lost acknowledgment drops applied ids, reissues only the same revision, and reports stale text", async () => {
  for (const outcome of ["applied", "same", "stale"] as const) {
    const current = structuredClone(base), sent: string[] = [], lost: TemplateQueuedIntent[] = [];
    if (outcome !== "same") current.workspace.projectRevision++;
    if (outcome === "applied") current.workspace.mutationReplay = [{ clientMutationId: "mutation", requestSha256: "a".repeat(64), resultingRevision: current.workspace.projectRevision }];
    let first = true, reads = 0;
    const queue = new RichSaveQueue({ durable: base, sessionId: "session", ports: {
      edit: request => {
        sent.push(request.clientMutationId);
        if (first) { first = false; throw new ProjectApiFailure("REVISION_CONFLICT", 409, { appliedClientMutationIds: [] }); }
        return Promise.resolve(result(current, request.clientMutationId));
      },
      read: () => { reads++; return Promise.resolve(current); }, adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {},
      lost: items => lost.push(...items),
    } });
    queue.template.enqueue(intent, "action", 0, "mutation");
    await queue.flush();
    assert.equal(reads, 1, outcome);
    assert.deepEqual(sent, outcome === "same" ? ["mutation", "mutation"] : ["mutation"], outcome);
    assert.deepEqual(lost.map(item => item.intent.operation), outcome === "stale" ? [intent.operation] : [], outcome);
    assert.equal(queue.template.pending.length, 0, outcome);
  }
});

test("service restart reopens then reads before deciding to reissue the same mutation", async () => {
  const paths: string[] = [];
  let unknown = true;
  const fetcher: Fetcher = (path, init) => {
    paths.push(path);
    if (path.endsWith("/open")) return Promise.resolve(Response.json({ schemaVersion: 1, editorToken: "new-editor-token", response: base, history: { undo: null, redo: null }, tasks: [] }));
    if (path.endsWith("/edits") && unknown) { unknown = false; return Promise.resolve(Response.json({ error: { code: "EDITOR_TOKEN_UNKNOWN" } }, { status: 409 })); }
    if (path.endsWith("/edits")) {
      const request = JSON.parse(String(init.body)) as { preparation: { clientMutationId: string } };
      return Promise.resolve(Response.json(result(base, request.preparation.clientMutationId)));
    }
    return Promise.resolve(Response.json(base));
  };
  const connection = await ProjectEditorConnection.open(base.workspace.projectId, fetcher);
  const queue = new RichSaveQueue({ durable: base, sessionId: "session", ports: {
    edit: (request, revision) => connection.edit(request, revision), read: () => connection.read(),
    adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {}, lost: () => assert.fail("lost"),
  } });
  queue.template.enqueue(intent, "action", 0, "mutation");
  await queue.flush();
  assert.deepEqual(paths.map(path => path.split("/").at(-1)), ["open", "edits", "open", base.workspace.projectId, "edits"]);
});

test("a superseded page shows the replaced state and sends no more requests", async () => {
  let requests = 0;
  const fetcher: Fetcher = () => { requests++; return Promise.resolve(Response.json({ error: { code: "EDITOR_REPLACED" } }, { status: 409 })); };
  const connection = new ProjectEditorConnection(base.workspace.projectId, "old-token", base, { undo: null, redo: null }, fetcher);
  await assert.rejects(connection.capture("capture", base.snapshot!, { kind: "blocks", blocks: [{ blockId: container.blockId, beforeRevision: 1 }] }), /EDITOR_REPLACED/);
  await assert.rejects(connection.capture("capture", base.snapshot!, { kind: "blocks", blocks: [{ blockId: container.blockId, beforeRevision: 1 }] }), /EDITOR_REPLACED/);
  assert.equal(requests, 1);
});

test("contiguous typing of one action is one request; a new action sends its own", async () => {
  const sent: string[] = [];
  const queue = new RichSaveQueue({ durable: base, sessionId: "session", ports: {
    edit: request => {
      const operation = request.operations[0];
      sent.push(operation && "text" in operation ? String(operation.text) : "");
      return Promise.resolve(result(base, request.clientMutationId));
    },
    read: () => Promise.resolve(base), adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {}, lost: () => assert.fail("lost"),
  } });
  const typed = (text: string, start: number): V7Intent => ({ localId: `op-${start}`, prior: intent.prior,
    operation: { kind: "replace_text", container, start, end: start, text, side: "before",
      styles: { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" } } });
  queue.template.enqueue(intent, "action", 0, "first");
  queue.template.enqueue(typed("Y", 9), "action", 1, "second");
  queue.template.enqueue(typed("Z", 10), "another", 0, "third");
  await queue.flush();
  assert.deepEqual(sent, ["XY", "Z"]);
});

test("closing the queue ignores a late reply and sends nothing after it", async () => {
  let release: (value: EditResult) => void = () => {};
  const sent: string[] = [], adopted: string[] = [];
  const queue = new RichSaveQueue({ durable: base, sessionId: "session", ports: {
    edit: request => { sent.push(request.clientMutationId); return new Promise(resolve => { release = resolve; }); },
    read: () => Promise.resolve(base), adopted: adoption => adopted.push(adoption.item.clientMutationId),
    changed: () => {}, retained: () => {}, released: () => {}, lost: () => assert.fail("lost"),
  } });
  queue.template.enqueue(intent, "action", 0, "first");
  queue.template.enqueue(intent, "another", 0, "second");
  const flushing = queue.flush();
  await new Promise(resolve => setImmediate(resolve));
  queue.close();
  release(result(base, "first"));
  await flushing;
  assert.deepEqual(sent, ["first"]);
  assert.deepEqual(adopted, []);
  assert.equal(queue.template.state.kind, "closed");
});
