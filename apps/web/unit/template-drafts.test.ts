import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import { TextSelection } from "@tiptap/pm/state";
import { attachTemplateWriter } from "../src/background/connection";
import { DraftRepository, type LocalDraft } from "../src/background/drafts";
import { sha256 } from "../src/background/wire";
import { contentText, responseBlocks } from "../src/contracts/template-address";
import { templateProjectWire } from "../src/contracts/template-validate";
import { isTemplateDraftPayload } from "../src/contracts/template-drafts";
import { templateSchema } from "../src/rich/template-schema";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { client, harness, type Harness } from "./support/template-harness";

function storage(): Storage {
  const values = new Map<string, string>();
  return { get length() { return values.size; }, clear: () => values.clear(), getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null, removeItem: key => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); } };
}
Object.assign(globalThis, { sessionStorage: storage(), localStorage: storage() });

type Browser = { rows: LocalDraft[]; repository: DraftRepository };
function browser(): Browser {
  const value: Browser = { rows: [], repository: new DraftRepository({ transact: work => {
    const next = work(value.rows); value.rows = next.rows; return Promise.resolve(next.result);
  }, discardProject: () => { value.rows = []; return Promise.resolve(); } }, () => Promise.reject(new Error("unused"))) };
  return value;
}
type Opened = { session: TemplateEditorSession; editor: TemplateEditor; warnings: string[] };

/** One tab opening: the exclusive-tab path suspends a crashed incarnation before reopening. */
async function open(value: Harness, local: Browser): Promise<Opened> {
  const warnings: string[] = [];
  const connection = await attachTemplateWriter(value.project, client(value, []), local.repository, () => true);
  assert.ok(connection?.proof, connection?.error ?? "attach failed");
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} }, 60_000);
  const response = await templateProjectWire(session.writer.durable);
  assert.ok(response?.workspace.project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(response.workspace.project.document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor, response.workspace.project.document);
  return { session, editor, warnings };
}
async function first(value: Harness, local: Browser): Promise<Opened> {
  // The harness fixture holds an attached writer; it detaches cleanly so this browser may open.
  const api = client(value, []), fixture = await api.templateRead(value.proof);
  await api.templateDetach({ schemaVersion: 2, proof: value.proof, canonicalRevision: fixture.writer.acknowledgedRevision,
    canonicalSha256: fixture.writer.acknowledgedSha256 ?? fixture.workspaceSha256, actionCursor: fixture.writer.acknowledgedCursor, touches: [] });
  return open(value, local);
}
/** A crash: nothing is flushed, detached or cleaned; only what was already retained survives. */
function crash(opened: Opened): void { opened.session.close(); opened.editor._tiptapEditor.destroy(); }
function start(editor: TemplateEditor, id: string): number {
  let found = -1;
  editor._tiptapEditor.state.doc.descendants((node, pos) => { if (node.type.name === "blockContainer" && node.attrs["id"] === id) found = pos + 2; return found < 0; });
  assert.ok(found >= 0, id); return found;
}
function type(editor: TemplateEditor, text: string): void {
  const tiptap = editor._tiptapEditor, pos = start(editor, "block-paper-a") + 16;
  tiptap.view.dispatch(tiptap.state.tr.setSelection(TextSelection.create(tiptap.state.doc, pos)));
  tiptap.view.dispatch(tiptap.state.tr.insertText(text, pos));
}
function saved(session: TemplateEditorSession): string {
  const group = responseBlocks(session.queue.template.durable).get("block-paper-a")?.groups[0];
  assert.ok(group); return contentText(group.content);
}
const settle = () => new Promise(resolve => setTimeout(resolve, 50));

test("crash before prepare: the retained input is saved once as a correction on reopen", async () => {
  const value = await harness(), local = browser();
  try {
    const a = await first(value, local);
    type(a.editor, "!");
    await settle();
    assert.equal(local.rows.length, 1, "input is retained locally before it is saved");
    crash(a);
    const b = await open(value, local);
    assert.equal(b.session.writer.mode, "recovering");
    assert.deepEqual(await b.session.recoverDraft(), { conflicts: 0 });
    assert.equal(saved(b.session), "By Shared title! / Journal North.");
    assert.equal(b.session.writer.mode, "normal");
    await settle();
    assert.equal(local.rows.length, 0, "a clean draft is removed");
    b.session.close();
  } finally { await value.close(); }
});

for (const legacy of [false, true]) test(`an unsaved split preserves its draft behind a recovery conflict (legacy=${String(legacy)})`, async () => {
  const value = await harness(), local = browser();
  try {
    const a = await first(value, local), tiptap = a.editor._tiptapEditor;
    tiptap.view.dispatch(tiptap.state.tr.setSelection(TextSelection.create(tiptap.state.doc, start(a.editor, "block-paper-a") + 10)));
    a.session.enter();
    await settle();
    let retained = local.rows[0]; assert.ok(retained);
    assert.match(retained.payloadWire, /"text":"By Shared"/);
    assert.match(retained.payloadWire, /"text":" title \/ Journal North\."/);
    if (legacy) {
      const payload: unknown = JSON.parse(retained.payloadWire);
      assert.ok(isTemplateDraftPayload(payload) && payload.templateQueue);
      payload.templateQueue.editorTexts = payload.templateQueue.editorTexts.filter(item => !item.container.blockId.startsWith("local-"));
      const payloadWire = JSON.stringify(payload);
      retained = { ...retained, payloadWire, payloadSha256: await sha256(payloadWire) };
      local.rows = [retained];
    }
    crash(a);
    const b = await open(value, local);
    assert.deepEqual(await b.session.recoverDraft(), { conflicts: 1 });
    assert.deepEqual(await b.session.recoverDraft("keep"), { conflicts: 1 });
    assert.equal(b.session.writer.mode, "recovering");
    assert.equal(saved(b.session), "By Shared title / Journal North.");
    assert.equal(local.rows[0]?.payloadWire, retained.payloadWire, "no partial correction or draft removal");
    await b.session.recoverDraft("saved");
    assert.equal(local.rows.length, 0);
    assert.equal(saved(b.session), "By Shared title / Journal North.");
    b.session.close();
  } finally { await value.close(); }
});

test("an unsaved merge retains both texts until a recovery conflict is resolved", async () => {
  const value = await harness(), local = browser();
  try {
    const a = await first(value, local), tiptap = a.editor._tiptapEditor;
    const leading = saved(a.session), trailing = responseBlocks(a.session.queue.template.durable).get("block-paper-b")?.groups[0];
    assert.ok(trailing);
    const trailingText = contentText(trailing.content);
    tiptap.view.dispatch(tiptap.state.tr.setSelection(TextSelection.create(tiptap.state.doc, start(a.editor, "block-paper-b"))));
    assert.equal(a.session.join("backward"), true);
    await settle();
    const retained = local.rows[0]; assert.ok(retained);
    const payload: unknown = JSON.parse(retained.payloadWire);
    assert.ok(isTemplateDraftPayload(payload) && payload.templateQueue);
    assert.equal(payload.templateQueue.editorTexts.find(item => item.container.blockId === "block-paper-a")?.text, leading + trailingText);
    assert.equal(payload.templateQueue.intents[0]?.operation.kind, "merge_blocks");
    crash(a);
    const b = await open(value, local);
    assert.deepEqual(await b.session.recoverDraft(), { conflicts: 1 });
    assert.deepEqual(await b.session.recoverDraft("keep"), { conflicts: 1 });
    assert.equal(b.session.writer.mode, "recovering");
    assert.equal(saved(b.session), leading);
    const unchanged = responseBlocks(b.session.queue.template.durable).get("block-paper-b")?.groups[0];
    assert.ok(unchanged); assert.equal(contentText(unchanged.content), trailingText);
    assert.equal(local.rows[0]?.payloadWire, retained.payloadWire);
    b.session.close();
  } finally { await value.close(); }
});

test("crash after prepare before the save was sent: the retained input is saved on reopen", async () => {
  const value = await harness(), local = browser();
  try {
    const a = await first(value, local), api = a.session.writer.connection.api;
    api.templateSavePrepared = () => Promise.reject(new TypeError("fetch failed"));
    type(a.editor, "!");
    await assert.rejects(a.session.flush(), /fetch failed/);
    await settle();
    const stored: unknown = JSON.parse(local.rows[0]?.payloadWire ?? "null");
    assert.match(JSON.stringify(stored), /"stage":"prepared"/);
    crash(a);
    const b = await open(value, local);
    await b.session.recoverDraft();
    assert.equal(saved(b.session), "By Shared title! / Journal North.");
    b.session.close();
  } finally { await value.close(); }
});

test("crash after commit before the local draft cleared: recovery finds nothing left to save", async () => {
  const value = await harness(), local = browser();
  try {
    const a = await first(value, local);
    const remove = local.repository.remove.bind(local.repository);
    local.repository.remove = () => Promise.reject(new Error("crashed before the local checkpoint"));
    type(a.editor, "!");
    await settle();
    await a.session.flush();
    await settle();
    assert.equal(local.rows.length, 1, "the stale draft still lists the committed intent");
    crash(a);
    local.repository.remove = remove;
    const b = await open(value, local);
    await b.session.recoverDraft();
    assert.equal(saved(b.session), "By Shared title! / Journal North.", "the committed text is not applied twice");
    b.session.close();
  } finally { await value.close(); }
});

test("crash after a server checkpoint: pending_input ends the server draft and the input saves", async () => {
  const value = await harness(), local = browser();
  try {
    const a = await first(value, local);
    type(a.editor, "!");
    await a.session.writer.checkpoint();
    crash(a);
    const b = await open(value, local);
    assert.ok(b.session.writer.connection.view.drafts.length, "the server holds the checkpoint");
    await b.session.recoverDraft();
    assert.equal(saved(b.session), "By Shared title! / Journal North.");
    assert.equal(b.session.writer.connection.view.drafts.length, 0);
    b.session.close();
  } finally { await value.close(); }
});

test("a container whose saved text moved needs an explicit choice; using the saved text keeps it", async () => {
  const value = await harness(), local = browser();
  try {
    const a = await first(value, local);
    type(a.editor, "!");
    await settle();
    crash(a);
    // The retained intent claims a different starting text, as if another writer changed the container meanwhile.
    const row = local.rows[0];
    assert.ok(row);
    const payloadWire = row.payloadWire.replaceAll('"text":"By Shared title / Journal North."', '"text":"Elsewhere"');
    local.rows = [{ ...row, payloadWire, payloadSha256: await sha256(payloadWire) }];
    const b = await open(value, local);
    assert.deepEqual(await b.session.recoverDraft(), { conflicts: 1 });
    assert.equal(b.session.writer.mode, "recovering", "nothing moves before the choice");
    await b.session.recoverDraft("saved");
    assert.equal(saved(b.session), "By Shared title / Journal North.");
    assert.equal(b.session.writer.mode, "normal");
    b.session.close();
  } finally { await value.close(); }
});

test("crash after a committed save whose reply was lost: the text is not applied twice", async () => {
  const value = await harness(), local = browser();
  try {
    const a = await first(value, local), api = a.session.writer.connection.api, save = api.templateSavePrepared.bind(api);
    api.templateSavePrepared = async (...args) => { await save(...args); throw new TypeError("fetch failed"); };
    type(a.editor, "!");
    await assert.rejects(a.session.flush(), /fetch failed/);
    await settle();
    crash(a);
    const b = await open(value, local);
    await b.session.recoverDraft();
    assert.equal(saved(b.session), "By Shared title! / Journal North.");
    await settle();
    assert.equal(local.rows.length, 0);
    b.session.close();
  } finally { await value.close(); }
});

test("keeping the editor text after a conflict saves it as a correction", async () => {
  const value = await harness(), local = browser();
  try {
    const a = await first(value, local);
    type(a.editor, "!");
    await settle();
    crash(a);
    const row = local.rows[0];
    assert.ok(row);
    const payloadWire = row.payloadWire.replaceAll('"text":"By Shared title / Journal North."', '"text":"Elsewhere"');
    local.rows = [{ ...row, payloadWire, payloadSha256: await sha256(payloadWire) }];
    const b = await open(value, local);
    assert.deepEqual(await b.session.recoverDraft(), { conflicts: 1 });
    await b.session.recoverDraft("keep");
    assert.equal(saved(b.session), "By Shared title! / Journal North.");
    b.session.close();
  } finally { await value.close(); }
});
