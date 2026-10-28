import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { errorMessage, knownErrorMessage } from "../src/errors/messages";
import { MemoryPendingStore, ProjectEditorConnection, type EditResult, type Fetcher, type HistoryState } from "../src/rich/v7-connection";
import { templateSchema } from "../src/rich/template-schema";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";

/** The editor session over a scripted /v2 service: undo, redo and save failures without a Python process. */
const base = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/projects/v7-response.json", import.meta.url), "utf8")) as TemplateProjectResponseV1;
const project = base.workspace.projectId;
const undoable: HistoryState = { undo: { actionId: "action-1", kind: "edit" }, redo: null };
const offline = () => Promise.reject(new TypeError("fetch failed"));

function revision(value: number): TemplateProjectResponseV1 {
  const response = structuredClone(base);
  response.workspace.projectRevision = value;
  return response;
}
function result(response: TemplateProjectResponseV1, id: string, history: HistoryState = { undo: null, redo: null }): EditResult {
  return { schemaVersion: 1, revision: response.workspace.projectRevision, documentRevision: response.workspace.documentRevision,
    clientMutationId: id, replayed: false, response, createdIds: {}, createdBlocks: {}, changedBlockIds: [], history };
}
type Route = (path: string, body: Record<string, unknown>) => Promise<Response> | Response;
function scripted(route: Route, paths: string[] = []): Fetcher {
  return async (path, init) => {
    paths.push(path.split("/").at(-1) ?? "");
    return route(path, typeof init.body === "string" ? JSON.parse(init.body) as Record<string, unknown> : {});
  };
}

async function opened(fetcher: Fetcher, history: HistoryState = undoable, store = new MemoryPendingStore()) {
  const warnings: string[] = [];
  const connection = new ProjectEditorConnection(project, "token", structuredClone(base), history, fetcher);
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} },
    60_000, store);
  const document = base.workspace.project?.document;
  assert.ok(document);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor);
  await session.recoverDraft();
  return { session, editor, warnings, store };
}
function type(editor: TemplateEditor, text: string): void {
  let at = -1;
  editor._tiptapEditor.state.doc.descendants((node, pos) => {
    if (node.type.name === "blockContainer" && node.attrs["id"] === "block-paper-a") at = pos + 2;
    return at < 0;
  });
  assert.ok(at >= 0);
  editor._tiptapEditor.view.dispatch(editor._tiptapEditor.state.tr.insertText(text, at + 9));
}
const settle = async () => { for (let turn = 0; turn < 5; turn++) await new Promise(resolve => setImmediate(resolve)); };

test("an undo whose outcome cannot be read is given up with a notice; input continues and the next save re-opens", async () => {
  let online = false;
  const paths: string[] = [];
  const { session, editor, warnings, store } = await opened(scripted((path, body) => {
    if (!online) return offline();
    if (path.endsWith("/open")) return Response.json({ schemaVersion: 1, editorToken: "token-2", response: revision(2), history: { undo: null, redo: null }, tasks: [] });
    return Response.json(result(revision(2), String((body["preparation"] as { clientMutationId: string }).clientMutationId)));
  }, paths));
  try {
    await session.navigate("undo");
    assert.deepEqual(warnings, [errorMessage(new TypeError("fetch failed"))]);
    assert.equal(store.records.get(project)?.navigation ?? null, null, "a reload does not repeat it");
    type(editor, "!");
    assert.equal(session.queue.template.pending.length, 1, "input is not blocked");
    online = true;
    await session.flush();
    assert.deepEqual(paths.slice(-2), ["edits", "open"]);
    assert.equal(session.canUndo, false);
  } finally { session.close(); }
});

test("a reloaded undo the server refuses is given up; the editor leaves recovery and follows the server", async () => {
  const store = new MemoryPendingStore();
  await store.save({ schemaVersion: 1, project, intents: [], locals: [],
    navigation: { direction: "undo", clientMutationId: "undo-1", expectedActionId: "action-1", baseRevision: 1 } });
  const { session, warnings } = await opened(scripted(path => {
    if (path.endsWith("/history")) return Response.json({ error: { code: "HISTORY_STALE" }, history: { undo: null, redo: null } }, { status: 409 });
    if (path.endsWith("/open")) return Response.json({ schemaVersion: 1, editorToken: "token-2", response: base, history: { undo: null, redo: null }, tasks: [] });
    return Response.json(base);
  }), undoable, store);
  try {
    assert.equal(session.mode, "normal");
    assert.equal(store.records.has(project), false);
    assert.deepEqual(warnings, [knownErrorMessage("HISTORY_STALE")]);
    assert.equal(session.canUndo, false);
  } finally { session.close(); }
});

test("a step refused as stale brings the server's history; the button follows it instead of repeating the refusal", async () => {
  let steps = 0;
  const { session, warnings } = await opened(scripted(() => {
    steps++;
    return Response.json({ error: { code: "HISTORY_STALE" }, history: { undo: null, redo: null } }, { status: 409 });
  }));
  try {
    assert.equal(session.canUndo, true);
    await session.navigate("undo");
    assert.equal(session.canUndo, false);
    await session.navigate("undo");
    assert.equal(steps, 1);
    assert.deepEqual(warnings, [knownErrorMessage("HISTORY_STALE")]);
  } finally { session.close(); }
});

test("a save without an answer is sent again on its own with the same id until it is acknowledged", async t => {
  const sent: string[] = [];
  const { session, editor } = await opened(scripted((_path, body) => {
    const id = (body["preparation"] as { clientMutationId: string }).clientMutationId;
    sent.push(id);
    return sent.length < 3 ? offline() : Response.json(result(revision(2), id));
  }));
  try {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    type(editor, "!");
    await assert.rejects(session.flush(), /fetch failed/);
    t.mock.timers.tick(1000);
    await settle();
    assert.equal(sent.length, 2);
    t.mock.timers.tick(1999);
    await settle();
    assert.equal(sent.length, 2, "the second retry waits longer");
    t.mock.timers.tick(1);
    await settle();
    assert.equal(new Set(sent).size, 1);
    assert.equal(sent.length, 3);
    assert.equal(session.queue.template.pending.length, 0);
  } finally { session.close(); }
});

test("a panel or structure command during an undo in flight waits and is expressed on the state the undo leaves", async () => {
  let release = () => {};
  const edits: number[] = [];
  const { session } = await opened(scripted(async (path, body) => {
    if (path.endsWith("/history")) {
      await new Promise<void>(resolve => { release = resolve; });
      return Response.json(result(revision(2), String(body["clientMutationId"]), { undo: null, redo: { actionId: "action-1", kind: "edit" } }));
    }
    const from = Number(body["baseRevision"]);
    edits.push(from);
    return Response.json(result(revision(from + 1), (body["preparation"] as { clientMutationId: string }).clientMutationId));
  }));
  try {
    const undo = session.navigate("undo");
    await settle();
    const removal = session.removeBlocks(["block-paper-b"]);
    await settle();
    assert.deepEqual(edits, [], "the command waits for the undo");
    release();
    await Promise.all([undo, removal]);
    assert.deepEqual(edits, [2]);
    assert.equal(session.queue.template.durable.workspace.projectRevision, 3);
  } finally { session.close(); }
});
