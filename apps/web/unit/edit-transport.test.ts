import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { RichSaveQueue, type TemplateQueuedIntent } from "../src/rich/save-queue";
import { ProjectApiFailure, ProjectEditorConnection, type EditResult, type Fetcher } from "../src/rich/v7-connection";
import { containerKey, type V7Intent } from "../src/rich/v7-translation";

const base = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/projects/v7-response.json", import.meta.url), "utf8")) as TemplateProjectResponseV1;
const container = { blockId: "block-paper-a", kind: "content" as const, cellId: null };
const paperA = "By Shared title / Journal North.";
const styles = { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" };
const intent: V7Intent = { localId: "op", prior: new Map([[containerKey(container), paperA]]),
  operation: { kind: "replace_text", container, start: 8, end: 8, text: "X", side: "interior", styles } };
/** Typing at offset 8 of one paragraph whose text was `prior` in the editor. */
function insert(localId: string, text: string, prior: string, blockId = container.blockId): V7Intent {
  const target = { ...container, blockId };
  return { localId, prior: new Map([[containerKey(target), prior]]),
    operation: { kind: "replace_text", container: target, start: 8, end: 8, text, side: "interior", styles } };
}
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

test("lost acknowledgment drops applied ids, reissues the same revision, translates again after a non-document commit, and reports stale text", async () => {
  for (const outcome of ["applied", "same", "export", "stale"] as const) {
    const current = structuredClone(base), sent: [string, number][] = [], lost: TemplateQueuedIntent[] = [];
    if (outcome !== "same") current.workspace.projectRevision++;
    // An export record or a rename moves only the project revision; another document change moves the document too.
    if (outcome === "stale") current.workspace.documentRevision++;
    if (outcome === "applied") current.workspace.mutationReplay = [{ clientMutationId: "mutation", requestSha256: "a".repeat(64), resultingRevision: current.workspace.projectRevision }];
    let first = true, reads = 0;
    const queue = new RichSaveQueue({ durable: base, sessionId: "session", ports: {
      edit: (request, revision) => {
        sent.push([request.clientMutationId, revision]);
        if (first) { first = false; throw new ProjectApiFailure("REVISION_CONFLICT", 409, { appliedClientMutationIds: [] }); }
        return Promise.resolve(result(current, request.clientMutationId));
      },
      read: () => { reads++; return Promise.resolve(current); }, adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {},
      lost: items => lost.push(...items),
    } });
    queue.template.enqueue(intent, "action", 0, "mutation");
    await queue.flush();
    assert.equal(reads, 1, outcome);
    assert.deepEqual(sent, { applied: [["mutation", 1]], same: [["mutation", 1], ["mutation", 1]], export: [["mutation", 1], ["mutation", 2]],
      stale: [["mutation", 1]] }[outcome], outcome);
    assert.deepEqual(lost.map(item => item.intent.operation), outcome === "stale" ? [intent.operation] : [], outcome);
    assert.equal(queue.template.pending.length, 0, outcome);
  }
});

test("unsent intents behind a recovered head are translated at their turn, never dropped for their enqueue revision", async () => {
  const after = structuredClone(base); after.workspace.projectRevision++;
  let current = base, first = true;
  const sent: string[] = [], lost: string[] = [];
  const queue = new RichSaveQueue({ durable: base, sessionId: "s", ports: {
    edit: request => {
      sent.push(request.clientMutationId);
      if (first) { first = false; throw new ProjectApiFailure("EDITOR_TOKEN_UNKNOWN", 409); }
      current = after; return Promise.resolve(result(after, request.clientMutationId));
    },
    read: () => Promise.resolve(current), adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {},
    lost: items => lost.push(...items.map(item => item.clientMutationId)),
  } });
  queue.template.enqueue(insert("op1", "X", paperA), "a1", 0, "m1");
  queue.template.enqueue(insert("op2", "Y", paperA), "a2", 0, "m2");
  await queue.flush();
  assert.deepEqual(sent, ["m1", "m1", "m2"]);
  assert.deepEqual(lost, []);
});

test("after a reload, an unsent intent behind an applied but unacknowledged head is sent", async () => {
  const after = structuredClone(base); after.workspace.projectRevision++;
  after.workspace.mutationReplay = [{ clientMutationId: "m1", requestSha256: "a".repeat(64), resultingRevision: after.workspace.projectRevision }];
  const sent: string[] = [], lost: string[] = [];
  const queue = new RichSaveQueue({ durable: base, sessionId: "s", ports: {
    edit: request => { sent.push(request.clientMutationId); return Promise.resolve(result(after, request.clientMutationId)); },
    read: () => Promise.resolve(after), adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {},
    lost: items => lost.push(...items.map(item => item.clientMutationId)),
  } });
  const capture = { sessionId: "s", actionId: "a1", actionToken: 0, dependencies: [] };
  queue.template.restore([
    { intent: insert("op1", "X", paperA), actionId: "a1", actionToken: 0, clientMutationId: "m1", baseRevision: 1,
      issued: { schemaVersion: 1, clientMutationId: "m1", snapshot: base.snapshot!, capture, operations: [] } as never },
    { intent: insert("op2", "Y", paperA), actionId: "a2", actionToken: 0, clientMutationId: "m2", baseRevision: 1, issued: null },
  ]);
  await queue.template.recoverPending();
  await queue.flush();
  assert.deepEqual(sent, ["m2"]);
  assert.deepEqual(lost, []);
});

test("after a lost acknowledgment, input the saved state cannot take is reported and later input still saves", async () => {
  // The head was not applied and the document changed; the second intent was typed on top of the head.
  const current = structuredClone(base); current.workspace.projectRevision++; current.workspace.documentRevision++;
  const sent: string[] = [], lost: string[] = [];
  let first = true;
  const queue = new RichSaveQueue({ durable: base, sessionId: "s", ports: {
    edit: request => {
      sent.push(request.clientMutationId);
      if (first) { first = false; throw new ProjectApiFailure("EDITOR_TOKEN_UNKNOWN", 409); }
      return Promise.resolve(result(current, request.clientMutationId));
    },
    read: () => Promise.resolve(current), adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {},
    lost: items => lost.push(...items.map(item => item.clientMutationId)),
  } });
  queue.template.enqueue(insert("op1", "X", paperA), "a1", 0, "m1");
  queue.template.enqueue(insert("op2", "Y", "By ShareXd title / Journal North."), "a2", 0, "m2");
  queue.template.enqueue(insert("op3", "Z", "Shared title", "block-paper-b"), "a3", 0, "m3");
  await queue.flush();
  assert.deepEqual(lost, ["m1", "m2"]);
  assert.deepEqual(sent, ["m1", "m3"]);
  assert.equal(queue.template.state.kind, "ready");
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
  // Nor does it open again, which would take the project back from the other page.
  await assert.rejects(connection.reopen(), /EDITOR_REPLACED/);
  assert.equal(requests, 1);
});

test("a refusal of the edit stops the queue with its reason; only a failure without an answer is sent again", async () => {
  const after = structuredClone(base); after.workspace.projectRevision++;
  const refusals = [["OUTCOME_UNKNOWN", 409], ["JOB_SCOPE_INVALID", 409], ["PROJECT_DELETED", 410], ["PROJECT_NOT_FOUND", 404],
    ["NOT_FOUND", 404], ["AUTH_REQUIRED", 401]] as const;
  for (const [code, status] of refusals) {
    const sent: string[] = [];
    const queue = new RichSaveQueue({ durable: base, sessionId: "session", ports: {
      edit: request => { sent.push(request.clientMutationId); return Promise.reject(new ProjectApiFailure(code, status)); },
      read: () => Promise.resolve(base), adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {}, lost: () => assert.fail("lost"),
    } });
    queue.template.enqueue(intent, "action", 0, "mutation");
    await assert.rejects(queue.flush(), /V7_INPUT_REJECTED/, code);
    await assert.rejects(queue.flush(), /V7_INPUT_REJECTED/, code);
    assert.deepEqual(queue.template.state, { kind: "rejected", reason: code });
    assert.deepEqual(sent, ["mutation"], code);
  }
  for (const failure of [new ProjectApiFailure("PROJECT_SAVE_FAILED", 503), new ProjectApiFailure("REQUEST_TIMEOUT", 408), new TypeError("fetch failed")]) {
    const sent: string[] = [];
    let fail = true;
    const queue = new RichSaveQueue({ durable: base, sessionId: "session", ports: {
      edit: request => {
        sent.push(request.clientMutationId);
        if (fail) { fail = false; return Promise.reject(failure); }
        return Promise.resolve(result(after, request.clientMutationId));
      },
      read: () => Promise.resolve(base), adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {}, lost: () => assert.fail("lost"),
    } });
    queue.template.enqueue(intent, "action", 0, "mutation");
    await assert.rejects(queue.flush());
    assert.equal(queue.template.state.kind, "ready");
    await queue.flush();
    assert.deepEqual(sent, ["mutation", "mutation"]);
    assert.equal(queue.template.pending.length, 0);
  }
});

/** A service that lost its editor tokens (a restart): an open replaces the current token at once and issues a new one;
 * `wait` holds a reply after its request was processed. */
function restartedService(wait: (path: string, id: string) => Promise<void>) {
  const state = { token: "token-after-restart", replaced: new Set<string>(), opens: 0, sent: [] as string[] };
  const fetcher: Fetcher = async (path, init) => {
    if (path.endsWith("/open")) {
      state.replaced.add(state.token);
      const token = state.token = `token-${++state.opens}`;
      await wait(path, "");
      return Response.json({ schemaVersion: 1, editorToken: token, response: base, history: { undo: null, redo: null }, tasks: [] });
    }
    const body = JSON.parse(String(init.body)) as { editorToken: string; clientCaptureId: string };
    state.sent.push(body.editorToken);
    const reply = body.editorToken === state.token ? Response.json({ clipboardCaptureId: body.clientCaptureId })
      : Response.json({ error: { code: state.replaced.has(body.editorToken) ? "EDITOR_REPLACED" : "EDITOR_TOKEN_UNKNOWN" } }, { status: 409 });
    await wait(path, body.clientCaptureId);
    return reply;
  };
  return { state, fetcher };
}
const selection: Parameters<ProjectEditorConnection["capture"]>[2] = { kind: "blocks", blocks: [{ blockId: container.blockId, beforeRevision: 1 }] };

test("requests that lose the token together share one re-open and the page keeps its editor", async () => {
  let releaseLate = () => {}, held = false;
  const { state, fetcher } = restartedService((path, id) => {
    if (id === "late" && !held) { held = true; return new Promise(resolve => { releaseLate = resolve; }); }
    return path.endsWith("/open") ? new Promise(resolve => setImmediate(resolve)) : Promise.resolve();
  });
  const connection = new ProjectEditorConnection(base.workspace.projectId, "token-before-restart", base, { undo: null, redo: null }, fetcher);
  // The lost token's answer to this one arrives only after the re-open; it is sent again without another open.
  const late = connection.capture("late", base.snapshot!, selection);
  await Promise.all([connection.capture("one", base.snapshot!, selection), connection.capture("two", base.snapshot!, selection)]);
  releaseLate();
  await late;
  assert.equal(state.opens, 1);
  assert.equal(state.sent.filter(token => token === "token-1").length, 3);
  assert.equal(connection.replaced, false);
});

test("a token this page re-opened past is sent again with the new one, not taken for another page", async () => {
  let release = () => {};
  const { state, fetcher } = restartedService(path => path.endsWith("/open") ? new Promise(resolve => { release = resolve; }) : Promise.resolve());
  state.token = "token-0";
  const connection = new ProjectEditorConnection(base.workspace.projectId, "token-0", base, { undo: null, redo: null }, fetcher);
  // The page re-opens (for example to refresh its history); the server has replaced the old token before the reply arrives.
  const reopening = connection.reopen();
  const capture = connection.capture("capture", base.snapshot!, selection);
  await new Promise(resolve => setImmediate(resolve));
  release();
  await Promise.all([reopening, capture]);
  assert.deepEqual(state.sent, ["token-0", "token-1"]);
  assert.equal(connection.replaced, false);
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

test("a read older than the adopted reply leaves the connection on the newer state", async () => {
  const older = structuredClone(base), newer = structuredClone(base);
  newer.workspace.projectRevision = older.workspace.projectRevision + 1;
  const fetcher: Fetcher = () => Promise.resolve(new Response(JSON.stringify(older), { status: 200 }));
  const connection = new ProjectEditorConnection("template-project", "token", newer, { undo: null, redo: null }, fetcher);
  assert.equal((await connection.read()).workspace.projectRevision, newer.workspace.projectRevision);
  assert.equal(connection.response.workspace.projectRevision, newer.workspace.projectRevision);
  const same = structuredClone(newer);
  same.workspace.documentRevision++;
  const again = new ProjectEditorConnection("template-project", "token", newer, { undo: null, redo: null },
    () => Promise.resolve(new Response(JSON.stringify(same), { status: 200 })));
  assert.equal((await again.read()).workspace.documentRevision, same.workspace.documentRevision, "an equal revision is a fresh read");
});

test("a replayed split without its created block re-reads the project and reports later input on it", async () => {
  const applied = structuredClone(base);
  applied.workspace.projectRevision++;
  applied.workspace.documentRevision++;
  const reads: string[] = [], lost: string[] = [], key = containerKey(container);
  const queue = new RichSaveQueue({ durable: base, sessionId: "session", ports: {
    edit: request => Promise.resolve({ ...result(applied, request.clientMutationId), replayed: true }),
    read: () => {
      reads.push("read");
      const current = structuredClone(applied);
      current.workspace.mutationReplay = [{ clientMutationId: "split", requestSha256: "0".repeat(64), resultingRevision: current.workspace.projectRevision }];
      return Promise.resolve(current);
    },
    adopted: () => {}, changed: () => {}, retained: () => {}, released: () => {},
    lost: items => lost.push(...items.map(item => item.clientMutationId)),
  } });
  queue.template.enqueue({ localId: "split-op", prior: new Map([[key, paperA]]),
    operation: { kind: "split_block", container, offset: 8, created: "local-1" } }, "action", 0, "split");
  queue.template.enqueue(insert("typed-op", "X", "", "local-1"), "action", 0, "typed");
  await queue.flush();
  assert.deepEqual(reads, ["read"]);
  assert.deepEqual(lost, ["typed"]);
  assert.equal(queue.template.state.kind, "ready");
  assert.equal(queue.template.pending.length, 0);
});
