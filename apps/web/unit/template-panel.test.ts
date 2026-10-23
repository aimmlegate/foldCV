import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import { TextSelection } from "@tiptap/pm/state";
import { attachTemplateWriter } from "../src/background/connection";
import { DraftRepository, type LocalDraft } from "../src/background/drafts";
import { jsonWireAt } from "../src/contracts/lossless-json";
import { contentText, responseBlocks } from "../src/contracts/template-address";
import { templateProjectWire } from "../src/contracts/template-validate";
import { templateSchema } from "../src/rich/template-schema";
import { employmentPanelCommands } from "../src/rich/v7-panel";
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

const kinds = new Map([["job", "employment"], ["tech", "technology"]]);
test("panel commands adapt to Python's V7 employment form; other kinds are refused", () => {
  assert.deepEqual(employmentPanelCommands({ operation: "edit", recordId: "job", values: { role: "Lead", "period:p1:start": "01.2021" } }, kinds),
    [{ operation: "edit", recordId: "job", values: { role: "Lead", "period:p1:start": "01.2021" } }]);
  assert.deepEqual(employmentPanelCommands({ operation: "remove_period", recordId: "job", periodId: "p1", values: { role: "Lead" } }, kinds),
    [{ operation: "edit", recordId: "job", values: { role: "Lead" } }, { operation: "remove_period", recordId: "job", periodId: "p1" }]);
  assert.deepEqual(employmentPanelCommands({ operation: "add_period", recordId: "job", values: {} }, kinds),
    [{ operation: "add_period", recordId: "job", values: {} }]);
  assert.deepEqual(employmentPanelCommands({ operation: "add", recordKind: "employment", values: { employer: "Acme", start: "01.2024" } }, kinds),
    [{ operation: "add", recordKind: "employment", values: { employer: "Acme", start: "01.2024" } }]);
  assert.equal(employmentPanelCommands({ operation: "edit", recordId: "tech", values: { display: "Go" } }, kinds), null);
  assert.equal(employmentPanelCommands({ operation: "edit", recordId: "job", values: {} }, kinds), null);
  assert.equal(employmentPanelCommands({ operation: "remove", recordId: "job", jobId: "job" }, kinds), null);
});

type Opened = { session: TemplateEditorSession; editor: TemplateEditor; warnings: string[] };
async function opened(value: Harness): Promise<Opened> {
  const api = client(value, []), warnings: string[] = [];
  let rows: LocalDraft[] = [];
  const repository = new DraftRepository({ transact: work => { const next = work(rows); rows = next.rows; return Promise.resolve(next.result); },
    discardProject: () => { rows = []; return Promise.resolve(); } }, () => Promise.reject(new Error("unused")));
  const fixture = await api.templateRead(value.proof);
  await api.templateDetach({ schemaVersion: 2, proof: value.proof, canonicalRevision: fixture.writer.acknowledgedRevision,
    canonicalSha256: fixture.writer.acknowledgedSha256 ?? fixture.workspaceSha256, actionCursor: fixture.writer.acknowledgedCursor, touches: [] });
  const connection = await attachTemplateWriter(value.project, api, repository);
  assert.ok(connection?.proof, connection?.error ?? "attach failed");
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} }, 60_000);
  const response = await templateProjectWire(session.writer.durable);
  assert.ok(response?.workspace.project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(response.workspace.project.document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor, response.workspace.project.document);
  return { session, editor, warnings };
}
function issues(session: TemplateEditorSession): Record<string, string> {
  const value = jsonWireAt(session.queue.template.durable, ["workspace", "project", "importIssues"]);
  return Object.fromEntries([...value.children.values()].map(issue => [String(jsonWireAt(issue, ["id"]).value), String(jsonWireAt(issue, ["state"]).value)]));
}
function employment(session: TemplateEditorSession): { id: string; role: string } {
  const records = jsonWireAt(session.queue.template.durable, ["workspace", "project", "facts", "records"]);
  const record = [...records.children.values()].find(item => jsonWireAt(item, ["kind"]).value === "employment");
  assert.ok(record);
  return { id: String(jsonWireAt(record, ["id"]).value), role: String(jsonWireAt(record, ["role", "rawText"]).value) };
}
function roleText(session: TemplateEditorSession): string {
  for (const block of responseBlocks(session.queue.template.durable).values()) {
    const group = block.groups[0];
    if (group?.kind === "content" && contentText(group.content).startsWith("Role: ")) return contentText(group.content);
  }
  return assert.fail("role paragraph missing");
}
/** The PM position just after the role field's last character, inside the field node. */
function roleEnd(editor: TemplateEditor): number {
  let found = -1;
  editor._tiptapEditor.state.doc.descendants((node, pos) => {
    if (node.type.name === "templateField" && node.attrs["fieldKey"] === "role") found = pos + 1 + node.content.size;
    return found < 0;
  });
  assert.ok(found > 0); return found;
}
function dispatch(editor: TemplateEditor, work: (tr: ReturnType<TemplateEditor["_tiptapEditor"]["state"]["tr"]["insertText"]>) => void): void {
  const tr = editor._tiptapEditor.state.tr; work(tr); editor._tiptapEditor.view.dispatch(tr);
}

test("a panel role edit saves through Python with input locked until its result is shown", async () => {
  const value = await harness("issues");
  const { session } = await opened(value);
  try {
    const job = employment(session);
    const done = session.panel({ operation: "edit", recordId: job.id, values: { role: "staff engineer" } });
    await done;
    assert.equal(employment(session).role, "staff engineer");
    assert.equal(roleText(session), "Role: staff engineer");
    assert.equal(session.writer.writable, true);
    assert.equal(session.history.length, 1, "one panel action");
  } finally { session.close(); await value.close(); }
});

test("E03: editing A retires only A; Undo restores it, Redo retires it, retyping the old wording keeps it retired", async () => {
  const value = await harness("issues");
  const { session, editor } = await opened(value);
  try {
    assert.deepEqual(issues(session), { "metric-warning": "active", "role-warning": "active" });
    const end = roleEnd(editor);
    dispatch(editor, tr => { tr.setSelection(TextSelection.create(tr.doc, end)); });
    dispatch(editor, tr => { tr.insertText("!", end); });
    await session.flush();
    assert.equal(roleText(session), "Role: backend engineer!");
    assert.deepEqual(issues(session), { "metric-warning": "active", "role-warning": "retired" });
    await session.navigate("undo");
    assert.deepEqual(issues(session), { "metric-warning": "active", "role-warning": "active" });
    assert.equal(roleText(session), "Role: backend engineer");
    await session.navigate("redo");
    assert.deepEqual(issues(session), { "metric-warning": "active", "role-warning": "retired" });
    // Restoring the original wording is a new edit; it does not reactivate the issue.
    const after = roleEnd(editor);
    dispatch(editor, tr => { tr.delete(after - 1, after); });
    await session.flush();
    assert.equal(roleText(session), "Role: backend engineer");
    assert.deepEqual(issues(session), { "metric-warning": "active", "role-warning": "retired" });
  } finally { session.close(); await value.close(); }
});

test("a panel command for a non-employment record is refused without touching the queue", async () => {
  const value = await harness("issues");
  const { session, warnings } = await opened(value);
  try {
    const records = jsonWireAt(session.queue.template.durable, ["workspace", "project", "facts", "records"]);
    const technology = [...records.children.values()].find(item => jsonWireAt(item, ["kind"]).value === "technology");
    assert.ok(technology);
    await assert.rejects(session.panel({ operation: "edit", recordId: String(jsonWireAt(technology, ["id"]).value), values: { display: "Go" } }),
      /V7_INPUT_UNSUPPORTED/);
    assert.equal(session.queue.template.pending.length, 0);
    assert.equal(warnings.length, 1);
  } finally { session.close(); await value.close(); }
});
