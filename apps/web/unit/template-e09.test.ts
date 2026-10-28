import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import { TextSelection } from "@tiptap/pm/state";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { MemoryPendingStore, type EditResult } from "../src/rich/v7-connection";
import { contentText, responseBlocks } from "../src/rich/v7-response";
import { templateSchema } from "../src/rich/template-schema";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { harness, projectClient, type Fault, type Harness, type Traffic } from "./support/template-harness";

async function open(value: Harness, local: MemoryPendingStore, fault: Fault | null = null) {
  const traffic: Traffic[] = [], warnings: string[] = [], connection = await projectClient(value, traffic, fault);
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} },
    60_000, local);
  const project = connection.response.workspace.project;
  assert.ok(project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(project.document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor, project.document);
  await session.recoverDraft();
  return { session, editor, traffic, warnings };
}

function pair(response: TemplateProjectResponseV1) {
  const project = response.workspace.project, job = project?.facts.records.find(record => record.kind === "employment");
  assert.ok(project && job?.kind === "employment");
  const issue = project.importIssues.find(item => item.id === "role-warning");
  assert.ok(issue);
  const role = [...responseBlocks(response).values()].flatMap(block => block.groups).find(group => contentText(group.content).startsWith("Role: "));
  assert.ok(role);
  return { text: contentText(role.content), fact: job.role.rawText, issue: issue.state, replays: response.workspace.mutationReplay.length };
}
function typeRole(editor: TemplateEditor, text: string): void {
  let end = -1;
  editor._tiptapEditor.state.doc.descendants((node, pos) => {
    if (node.type.name === "templateField" && node.attrs["fieldKey"] === "role") end = pos + 1 + node.content.size;
    return end < 0;
  });
  assert.ok(end > 0);
  const tiptap = editor._tiptapEditor;
  tiptap.view.dispatch(tiptap.state.tr.setSelection(TextSelection.create(tiptap.state.doc, end)));
  tiptap.view.dispatch(tiptap.state.tr.insertText(text, end));
}

test("E09: an unsent edit keeps the old text, fact and issue; retry commits the pair once", async () => {
  const value = await harness("issues"), local = new MemoryPendingStore();
  const opened = await open(value, local, { path: "/edits", times: 1, before: true });
  try {
    const before = pair(opened.session.queue.template.durable);
    typeRole(opened.editor, "!");
    await assert.rejects(opened.session.flush(), /fetch failed/);
    assert.deepEqual(pair(await opened.session.connection.read()), before);
    await opened.session.flush();
    const after = pair(opened.session.queue.template.durable);
    assert.deepEqual([after.text, after.fact, after.issue, after.replays], ["Role: backend engineer!", "backend engineer!", "retired", before.replays + 1]);
    const wires = opened.traffic.filter(entry => entry.path.endsWith("/edits")).map(entry => entry.wire);
    assert.equal(wires.length, 2);
    assert.equal(wires[0], wires[1]);
  } finally { opened.session.close(); await value.close(); }
});

test("E09: a lost reply retries one id and never repeats the text or revives its issue", async () => {
  const value = await harness("issues"), opened = await open(value, new MemoryPendingStore(), { path: "/edits", times: 1 });
  try {
    typeRole(opened.editor, "!");
    await assert.rejects(opened.session.flush(), /fetch failed/);
    const committed = pair(await opened.session.connection.read());
    await opened.session.flush();
    assert.deepEqual(pair(opened.session.queue.template.durable), committed);
    assert.equal(committed.text, "Role: backend engineer!");
    assert.equal(committed.issue, "retired");
  } finally { opened.session.close(); await value.close(); }
});

test("E09: reopening replays a pending intent once and preserves the coherent pair", async () => {
  const value = await harness("issues"), local = new MemoryPendingStore();
  try {
    const first = await open(value, local);
    typeRole(first.editor, "!");
    await first.session.retain();
    assert.equal(local.records.size, 1);
    first.session.close();
    const second = await open(value, local);
    try {
      const after = pair(second.session.queue.template.durable);
      assert.deepEqual([after.text, after.fact, after.issue], ["Role: backend engineer!", "backend engineer!", "retired"]);
      assert.equal(local.records.size, 0);
      second.session.close();
      const third = await open(value, local);
      try { assert.deepEqual(pair(third.session.queue.template.durable), after); }
      finally { third.session.close(); }
    } finally { second.session.close(); }
  } finally { await value.close(); }
});

test("an Undo in flight when the page closes runs once with its original id after a restart", async () => {
  const value = await harness("issues"), local = new MemoryPendingStore();
  let first: Awaited<ReturnType<typeof open>> | null = null;
  try {
    first = await open(value, local);
    const before = pair(first.session.queue.template.durable);
    typeRole(first.editor, "!");
    await first.session.flush();
    // The page closes while its history request is on the way.
    let sending = () => {};
    const sent = new Promise<void>(resolve => { sending = resolve; });
    first.session.connection.step = () => { sending(); return new Promise<EditResult>(() => {}); };
    void first.session.navigate("undo");
    await sent;
    const pending = await local.load(value.project);
    assert.ok(pending?.navigation);
    first.session.close();
    const second = await open(value, local);
    try {
      const undone = pair(second.session.queue.template.durable);
      assert.deepEqual([undone.text, undone.fact, undone.issue], [before.text, before.fact, before.issue]);
      const history = second.traffic.filter(entry => entry.path.endsWith("/history"));
      assert.equal(history.length, 1);
      assert.equal((JSON.parse(history[0]?.wire ?? "null") as { clientMutationId: string }).clientMutationId, pending.navigation.clientMutationId);
      assert.equal(local.records.size, 0);
      assert.equal(second.session.canRedo, true);
    } finally { second.session.close(); }
  } finally { first?.session.close(); await value.close(); }
});

test("an Undo that cannot be sent is given up with a notice; input continues and a restart does not repeat it", async () => {
  const value = await harness("issues"), local = new MemoryPendingStore(), fault: Fault = { path: "/history", times: 2, before: true };
  const opened = await open(value, local, fault);
  try {
    typeRole(opened.editor, "!");
    await opened.session.flush();
    await opened.session.navigate("undo");
    assert.equal(fault.times, 0);
    assert.equal(opened.warnings.length, 1);
    assert.equal((await local.load(value.project))?.navigation ?? null, null);
    typeRole(opened.editor, "?");
    await opened.session.flush();
    assert.equal(pair(opened.session.queue.template.durable).text, "Role: backend engineer!?");
  } finally { opened.session.close(); await value.close(); }
});
