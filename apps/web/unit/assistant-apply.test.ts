import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { MemoryPendingStore, ProjectApiFailure, ProjectEditorConnection, type EditResult, type Fetcher } from "../src/rich/v7-connection";
import { templateSchema } from "../src/rich/template-schema";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { proposal } from "./support/assistant";

const base = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/projects/v7-response.json", import.meta.url), "utf8")) as TemplateProjectResponseV1;
const PROJECT = base.workspace.projectId;

function applied(): TemplateProjectResponseV1 {
  const response = structuredClone(base), project = response.workspace.project;
  assert.ok(project);
  const block = project.document.regions.flatMap(region => region.blocks).find(item => item.id === "block-paper-a");
  assert.ok(block && Array.isArray(block.content));
  const first = block.content[0];
  assert.ok(first && "text" in first);
  first.text = "Written by ";
  block.revision++;
  response.workspace.projectRevision++; response.workspace.documentRevision++;
  return response;
}
function result(response: TemplateProjectResponseV1, id: string, undo: string | null, redo: string | null): EditResult {
  return { schemaVersion: 1, revision: response.workspace.projectRevision, documentRevision: response.workspace.documentRevision,
    clientMutationId: id, replayed: false, response, createdIds: {}, createdBlocks: {}, changedBlockIds: ["block-paper-a"],
    history: { undo: undo ? { actionId: undo, kind: "edit" } : null, redo: redo ? { actionId: redo, kind: "edit" } : null } };
}
type Sent = { path: string; body: Record<string, unknown> };
function server(apply: (body: Record<string, unknown>, attempt: number) => Response | Promise<Response>) {
  const sent: Sent[] = [];
  let attempts = 0, token = "token-1";
  const fetcher: Fetcher = async (path, init) => {
    const body = typeof init.body === "string" ? JSON.parse(init.body) as Record<string, unknown> : {};
    sent.push({ path, body });
    if (path.endsWith("/open")) return Response.json({ schemaVersion: 1, editorToken: token, response: base, history: { undo: null, redo: null }, tasks: [] });
    if (path.endsWith("/apply")) return apply(body, ++attempts);
    if (path.endsWith("/history")) return Response.json(result(base, String(body["clientMutationId"]), null, "proposal-1"));
    return Response.json(base);
  };
  return { sent, fetcher, rotate: (next: string) => { token = next; } };
}
async function opened(fetcher: Fetcher): Promise<{ session: TemplateEditorSession; editor: TemplateEditor }> {
  const connection = await ProjectEditorConnection.open(PROJECT, fetcher);
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: () => {}, mode: () => {}, shown: () => {} }, 60_000,
    new MemoryPendingStore());
  const project = session.queue.template.durable.workspace.project;
  assert.ok(project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(project.document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor);
  await session.recoverDraft();
  return { session, editor };
}
const shownText = (editor: TemplateEditor) => editor._tiptapEditor.state.doc.textContent;
const applyReply = (body: Record<string, unknown>) => Response.json({ proposal: { ...proposal(), state: "applied", appliedRevision: 2 },
  edit: result(applied(), String(body["clientMutationId"]), "proposal-1", null), action: null });

test("Apply sends the page token and edits flag, shows the committed text and adds one undo action", async () => {
  const { sent, fetcher } = server(applyReply);
  const { session, editor } = await opened(fetcher);
  try {
    const reply = await session.applyAssistant("proposal-1", true);
    assert.equal(reply.proposal.state, "applied");
    const request = sent.find(item => item.path.endsWith("/assistant/proposals/proposal-1/apply"));
    assert.ok(request);
    assert.equal(request.body["editorToken"], "token-1");
    assert.equal(request.body["allowEdits"], true);
    assert.equal(typeof request.body["clientMutationId"], "string");
    assert.ok(shownText(editor).includes("Written by "));
    assert.equal(session.canUndo, true);
    assert.equal(session.connection.history.undo?.actionId, "proposal-1");
    await session.navigate("undo");
    const undo = sent.find(item => item.path.endsWith("/history"));
    assert.equal(undo?.body["expectedActionId"], "proposal-1", "one Undo targets the whole proposal");
    assert.ok(!shownText(editor).includes("Written by "));
    assert.equal(session.mode, "normal");
  } finally { session.close(); }
});

test("a lost Apply reply repeats the same mutation id once; a refusal is shown and changes nothing", async () => {
  const ids: unknown[] = [];
  const { fetcher } = server((body, attempt) => {
    ids.push(body["clientMutationId"]);
    if (attempt === 1) throw new TypeError("fetch failed");
    return applyReply(body);
  });
  const { session, editor } = await opened(fetcher);
  try {
    await session.applyAssistant("proposal-1", true);
    assert.equal(ids.length, 2); assert.equal(ids[0], ids[1]);
    assert.ok(shownText(editor).includes("Written by "));
  } finally { session.close(); }

  const stale = server(() => Response.json({ error: { code: "ASSISTANT_PROPOSAL_STALE", targets: ["block-paper-a"] } }, { status: 409 }));
  const second = await opened(stale.fetcher);
  try {
    await assert.rejects(second.session.applyAssistant("proposal-1", true),
      (error: unknown) => error instanceof ProjectApiFailure && error.code === "ASSISTANT_PROPOSAL_STALE");
    assert.equal(stale.sent.filter(item => item.path.endsWith("/apply")).length, 1, "a refusal is not retried");
    assert.ok(!shownText(second.editor).includes("Written by "));
    assert.equal(second.session.mode, "normal");
  } finally { second.session.close(); }
});

test("a replaced page turns read-only; an unknown token re-opens and repeats the same request", async () => {
  const replaced = server(() => Response.json({ error: { code: "EDITOR_REPLACED" } }, { status: 409 }));
  const first = await opened(replaced.fetcher);
  try {
    await assert.rejects(first.session.applyAssistant("proposal-1", true), /EDITOR_REPLACED/u);
    assert.equal(first.session.mode, "read_only");
  } finally { first.session.close(); }

  const restarted = server((body, attempt) => attempt === 1
    ? Response.json({ error: { code: "EDITOR_TOKEN_UNKNOWN" } }, { status: 409 }) : applyReply(body));
  const second = await opened(restarted.fetcher);
  try {
    restarted.rotate("token-2");
    await second.session.applyAssistant("proposal-1", true);
    const applies = restarted.sent.filter(item => item.path.endsWith("/apply"));
    assert.deepEqual(applies.map(item => item.body["editorToken"]), ["token-1", "token-2"]);
    assert.equal(applies[0]?.body["clientMutationId"], applies[1]?.body["clientMutationId"]);
    assert.ok(shownText(second.editor).includes("Written by "));
  } finally { second.session.close(); }
});
