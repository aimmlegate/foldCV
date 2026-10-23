import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import { TextSelection } from "@tiptap/pm/state";
import { attachTemplateWriter } from "../src/background/connection";
import { DraftRepository, type LocalDraft } from "../src/background/drafts";
import { jsonWireAt, parseJsonWire, type JsonWireNode } from "../src/contracts/lossless-json";
import { contentText, responseBlocks } from "../src/contracts/template-address";
import { templateProjectWire } from "../src/contracts/template-validate";
import { templateSchema } from "../src/rich/template-schema";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { client, harness, type Fault, type Harness, type Traffic } from "./support/template-harness";

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
type Opened = { session: TemplateEditorSession; editor: TemplateEditor; traffic: Traffic[] };
async function open(value: Harness, local: Browser, fault: Fault | null = null): Promise<Opened> {
  const traffic: Traffic[] = [];
  const connection = await attachTemplateWriter(value.project, client(value, traffic, fault), local.repository, () => true);
  assert.ok(connection?.proof, connection?.error ?? "attach failed");
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: () => {}, mode: () => {}, shown: () => {} }, 60_000);
  const response = await templateProjectWire(session.writer.durable);
  assert.ok(response?.workspace.project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(response.workspace.project.document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor, response.workspace.project.document);
  return { session, editor, traffic };
}
async function first(value: Harness, local: Browser, fault: Fault | null = null): Promise<Opened> {
  const api = client(value, []), fixture = await api.templateRead(value.proof);
  await api.templateDetach({ schemaVersion: 2, proof: value.proof, canonicalRevision: fixture.writer.acknowledgedRevision,
    canonicalSha256: fixture.writer.acknowledgedSha256 ?? fixture.workspaceSha256, actionCursor: fixture.writer.acknowledgedCursor, touches: [] });
  return open(value, local, fault);
}
function crash(opened: Opened): void { opened.session.close(); opened.editor._tiptapEditor.destroy(); }
const settle = () => new Promise(resolve => setTimeout(resolve, 50));

/** The coherent pair E09 checks: the role text, the employment fact and the role issue state, read from one record. */
function pair(root: JsonWireNode): { text: string; fact: string; issue: string; replays: number } {
  let text = "";
  for (const block of responseBlocks(root).values()) {
    const group = block.groups[0];
    if (group?.kind === "content" && contentText(group.content).startsWith("Role: ")) text = contentText(group.content);
  }
  const project = jsonWireAt(root, ["workspace", "project"]);
  const records = [...jsonWireAt(project, ["facts", "records"]).children.values()];
  const job = records.find(record => jsonWireAt(record, ["kind"]).value === "employment");
  assert.ok(job);
  const issue = [...jsonWireAt(project, ["importIssues"]).children.values()].find(item => jsonWireAt(item, ["id"]).value === "role-warning");
  assert.ok(issue);
  return { text, fact: String(jsonWireAt(job, ["role", "rawText"]).value), issue: String(jsonWireAt(issue, ["state"]).value),
    replays: jsonWireAt(root, ["workspace", "mutationReplay"]).children.size };
}
/** What the store holds now, read losslessly with the session's own proof. */
async function disk(value: Harness, session: TemplateEditorSession): Promise<ReturnType<typeof pair>> {
  const response = await fetch(`${value.origin}/v1/rich/projects/${value.project}/writer/read`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(session.writer.proof) });
  assert.equal(response.status, 200);
  return pair(jsonWireAt(parseJsonWire(await response.text()), ["response"]));
}
function roleEnd(editor: TemplateEditor): number {
  let found = -1;
  editor._tiptapEditor.state.doc.descendants((node, pos) => {
    if (node.type.name === "templateField" && node.attrs["fieldKey"] === "role") found = pos + 1 + node.content.size;
    return found < 0;
  });
  assert.ok(found > 0); return found;
}
function typeRole(editor: TemplateEditor, text: string): void {
  const tiptap = editor._tiptapEditor, end = roleEnd(editor);
  tiptap.view.dispatch(tiptap.state.tr.setSelection(TextSelection.create(tiptap.state.doc, end)));
  tiptap.view.dispatch(tiptap.state.tr.insertText(text, end));
}

test("E09: a save that never reached Python leaves the coherent prior pair; the retry saves text, fact and issue together once", async () => {
  const value = await harness("issues"), local = browser(), fault: Fault = { path: "/save", times: 1, before: true };
  const a = await first(value, local, fault);
  try {
    const before = pair(a.session.queue.template.durable);
    assert.deepEqual([before.text, before.fact, before.issue], ["Role: backend engineer", "backend engineer", "active"]);
    typeRole(a.editor, "!");
    await assert.rejects(a.session.flush(), /fetch failed/);
    assert.equal(fault.times, 0, "the save was dropped unsent");
    assert.deepEqual(await disk(value, a.session), before, "the record keeps the prior text, fact and active issue");
    await a.session.flush();
    const after = pair(a.session.queue.template.durable);
    assert.deepEqual([after.text, after.fact, after.issue, after.replays], ["Role: backend engineer!", "backend engineer!", "retired", before.replays + 1]);
    assert.deepEqual(await disk(value, a.session), after);
  } finally { a.session.close(); await value.close(); }
});

test("E09: an older reply injected for a later save is not adopted; recovery finds the real commit and nothing applies twice", async () => {
  const value = await harness("issues"), local = browser(), fault: Fault = { path: "/save", times: 0 };
  const a = await first(value, local, fault);
  try {
    typeRole(a.editor, "!");
    await a.session.flush();
    const older = [...a.traffic].reverse().find(entry => entry.path.endsWith("/save"))?.reply;
    assert.ok(older);
    const once = pair(a.session.queue.template.durable);
    // The next save is processed, but its reply is replaced by the previous save's reply.
    fault.times = 1; fault.replace = older;
    typeRole(a.editor, "?");
    await a.session.flush();
    assert.equal(fault.times, 0, "the older reply was delivered");
    assert.equal(a.traffic.filter(entry => entry.path.endsWith("/read")).length > 0, true, "recovery read the durable record");
    const after = pair(a.session.queue.template.durable);
    assert.deepEqual([after.text, after.fact, after.issue, after.replays], ["Role: backend engineer!?", "backend engineer!?", "retired", once.replays + 1]);
    assert.deepEqual(await disk(value, a.session), after);
    assert.equal(a.session.writer.mode, "normal");
  } finally { a.session.close(); await value.close(); }
});

test("E09: a crash after the edit keeps it locally; reopen saves it once and the issue stays retired after another reopen", async () => {
  const value = await harness("issues"), local = browser();
  try {
    const a = await first(value, local);
    typeRole(a.editor, "!");
    await settle();
    assert.equal(local.rows.length, 1);
    crash(a);
    const b = await open(value, local);
    assert.equal(b.session.writer.mode, "recovering");
    assert.deepEqual(await b.session.recoverDraft(), { conflicts: 0 });
    const recovered = pair(b.session.queue.template.durable);
    assert.deepEqual([recovered.text, recovered.fact, recovered.issue], ["Role: backend engineer!", "backend engineer!", "retired"]);
    await b.session.writer.navigate();
    b.session.close();
    const c = await open(value, local);
    try {
      assert.equal(c.session.writer.mode, "normal");
      assert.deepEqual(pair(c.session.queue.template.durable), recovered, "no resurrection after reopen");
    } finally { c.session.close(); }
  } finally { await value.close(); }
});
