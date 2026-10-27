import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import { TextSelection } from "@tiptap/pm/state";
import { contentText, responseBlocks } from "../src/rich/v7-response";
import { templateSchema } from "../src/rich/template-schema";
import { employmentPanelCommands } from "../src/rich/v7-panel";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { projectClient, harness, type Harness, type Traffic } from "./support/template-harness";

function storage(): Storage {
  const values = new Map<string, string>();
  return { get length() { return values.size; }, clear: () => values.clear(), getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null, removeItem: key => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); } };
}
Object.assign(globalThis, { sessionStorage: storage(), localStorage: storage() });

const kinds = new Map([["job", "employment"], ["tech", "technology"]]);
test("panel commands adapt to Python's V7 employment form; a technology reorder is forwarded", () => {
  assert.deepEqual(employmentPanelCommands({ operation: "edit", recordId: "job", values: { role: "Lead", "period:p1:start": "01.2021" } }, kinds),
    [{ operation: "edit", recordId: "job", values: { role: "Lead", "period:p1:start": "01.2021" } }]);
  assert.deepEqual(employmentPanelCommands({ operation: "remove_period", recordId: "job", periodId: "p1", values: { role: "Lead" } }, kinds),
    [{ operation: "edit", recordId: "job", values: { role: "Lead" } }, { operation: "remove_period", recordId: "job", periodId: "p1" }]);
  assert.deepEqual(employmentPanelCommands({ operation: "add_period", recordId: "job", values: {} }, kinds),
    [{ operation: "add_period", recordId: "job", values: {} }]);
  assert.deepEqual(employmentPanelCommands({ operation: "add", recordKind: "employment", values: { employer: "Acme", start: "01.2024" } }, kinds),
    [{ operation: "add", recordKind: "employment", values: { employer: "Acme", start: "01.2024" } }]);
  assert.deepEqual(employmentPanelCommands({ operation: "move_technology", recordId: "tech", beforeRecordId: "other" }, kinds),
    [{ operation: "move_technology", recordId: "tech", beforeRecordId: "other" }]);
  assert.deepEqual(employmentPanelCommands({ operation: "move_technology", recordId: "tech", beforeRecordId: null }, kinds),
    [{ operation: "move_technology", recordId: "tech" }]);
  assert.equal(employmentPanelCommands({ operation: "edit", recordId: "tech", values: { display: "Go" } }, kinds), null);
  assert.equal(employmentPanelCommands({ operation: "move_technology", recordId: "job", beforeRecordId: "tech" }, kinds), null);
  assert.equal(employmentPanelCommands({ operation: "move_focus", recordId: "tech", beforeRecordId: "other" }, kinds), null);
  assert.equal(employmentPanelCommands({ operation: "edit", recordId: "job", values: {} }, kinds), null);
  assert.equal(employmentPanelCommands({ operation: "remove", recordId: "job", jobId: "job" }, kinds), null);
});

type Opened = { session: TemplateEditorSession; editor: TemplateEditor; warnings: string[] };
async function opened(value: Harness): Promise<Opened> {
  const warnings: string[] = [];
  const traffic: Traffic[] = [];
  const connection = await projectClient(value, traffic);
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} }, 60_000);
  const response = session.queue.template.durable;
  assert.ok(response?.workspace.project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(response.workspace.project.document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor, response.workspace.project.document);
  await session.recoverDraft();
  return { session, editor, warnings };
}
function issues(session: TemplateEditorSession): Record<string, string> {
  return Object.fromEntries((session.queue.template.durable.workspace.project?.importIssues ?? []).map(issue => [issue.id, issue.state]));
}
function employment(session: TemplateEditorSession): { id: string; role: string } {
  const record = session.queue.template.durable.workspace.project?.facts.records.find(item => item.kind === "employment");
  assert.ok(record?.kind === "employment");
  return { id: record.id, role: record.role.rawText };
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
    assert.equal(session.writable, true);
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
    const technology = session.queue.template.durable.workspace.project?.facts.records.find(item => item.kind === "technology");
    assert.ok(technology);
    await assert.rejects(session.panel({ operation: "edit", recordId: technology.id, values: { display: "Go" } }),
      /V7_INPUT_UNSUPPORTED/);
    assert.equal(session.queue.template.pending.length, 0);
    assert.equal(warnings.length, 1);
  } finally { session.close(); await value.close(); }
});
