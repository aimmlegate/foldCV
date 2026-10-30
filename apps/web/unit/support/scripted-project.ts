import { BlockNoteEditor } from "@blocknote/core";
import { TextSelection } from "@tiptap/pm/state";
import type { TemplateProjectResponseV1 } from "../../src/contracts/generated/template_project_response_v1";
import { MemoryPendingStore, ProjectEditorConnection, type EditResult } from "../../src/rich/v7-connection";
import { templateSchema } from "../../src/rich/template-schema";
import { projectTemplateDocument } from "../../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../../src/rich/v7-session";

/** A session over a scripted server: for replies a real Python service would need a rare state to give. */
export type Paragraph = { id: string; text: string; bold?: boolean };
export type Wire = { operation: { kind: string; text?: string }; clientMutationId: string; body: Record<string, unknown> };
export type Reply = { status: number; body: unknown };
export type Handler = (path: string, request: Wire | null) => Reply | Promise<Reply>;

export function response(paragraphs: readonly Paragraph[], revision: number, replay: readonly string[] = []): TemplateProjectResponseV1 {
  return JSON.parse(JSON.stringify({ schemaVersion: 1, durability: "durable", presentation: null,
    snapshot: { projectId: "p", projectRevision: revision, documentRevision: revision, documentHash: "d", factsHash: "f", packageHash: "k", presentationHash: "x" },
    workspace: { projectId: "p", projectRevision: revision, documentRevision: revision, mutationReplay: replay.map(clientMutationId => ({ clientMutationId })),
      project: { facts: { revision: 1, records: [], extensions: [] }, importIssues: [], sources: [], templatePackage: { assets: [] },
        document: { regions: [{ id: "r", role: "main", blocks: paragraphs.map(value => ({ id: value.id, type: "paragraph", revision: 1, props: {},
          content: value.text ? [{ type: "text", text: value.text, styles: value.bold ? { bold: true } : {} }] : [], children: [] })) }] } } } })) as TemplateProjectResponseV1;
}

export function saved(value: TemplateProjectResponseV1, clientMutationId: string, extra: Partial<EditResult> = {}): Reply {
  return { status: 200, body: { schemaVersion: 1, revision: value.workspace.projectRevision, documentRevision: value.workspace.documentRevision,
    clientMutationId, replayed: false, createdIds: {}, createdBlocks: {}, changedBlockIds: [], history: { undo: null, redo: null }, response: value, ...extra } };
}
export const refused = (code: string, status = 422): Reply => ({ status, body: { error: { code } } });

function wire(text: unknown): Wire | null {
  if (typeof text !== "string") return null;
  const body: unknown = JSON.parse(text);
  if (typeof body !== "object" || body === null) return null;
  const preparation: unknown = Reflect.get(body, "preparation");
  const operations: unknown = typeof preparation === "object" && preparation !== null ? Reflect.get(preparation, "operations") : null;
  const first: unknown = Array.isArray(operations) ? operations[0] : null;
  return { operation: { kind: typeof first === "object" && first !== null ? String(Reflect.get(first, "kind")) : "",
    ...typeof first === "object" && first !== null && typeof Reflect.get(first, "text") === "string" ? { text: String(Reflect.get(first, "text")) } : {} },
  clientMutationId: typeof preparation === "object" && preparation !== null ? String(Reflect.get(preparation, "clientMutationId")) : "",
  body: Object.fromEntries(Object.entries(body)) };
}

export type Scripted = { session: TemplateEditorSession; editor: TemplateEditor; connection: ProjectEditorConnection; warnings: string[] };
export async function scripted(initial: TemplateProjectResponseV1, handler: Handler, rewriteInterval = 1): Promise<Scripted> {
  const connection = new ProjectEditorConnection("p", "t", initial, { undo: { actionId: "server-a", kind: "edit" }, redo: null }, async (path, init) => {
    const { status, body } = await handler(path, wire(init.body));
    return new Response(JSON.stringify(body), { status });
  });
  const warnings: string[] = [];
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} }, 60_000,
    new MemoryPendingStore(), rewriteInterval);
  const document = initial.workspace.project?.document;
  if (!document) throw new Error("no document");
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor);
  await session.recoverDraft();
  return { session, editor, connection, warnings };
}

export function blockStart(editor: TemplateEditor, id: string): number {
  let found = -1;
  editor._tiptapEditor.state.doc.descendants((node, pos) => { if (node.type.name === "blockContainer" && node.attrs["id"] === id) found = pos + 2; return found < 0; });
  if (found < 0) throw new Error(id);
  return found;
}
export function type(editor: TemplateEditor, text: string, pos: number): void {
  editor._tiptapEditor.view.dispatch(editor._tiptapEditor.state.tr.insertText(text, pos));
}
export function select(editor: TemplateEditor, anchor: number, head = anchor): void {
  const state = editor._tiptapEditor.state;
  editor._tiptapEditor.view.dispatch(state.tr.setSelection(TextSelection.create(state.doc, anchor, head)));
}
export function paragraphs(editor: TemplateEditor): string[] {
  const result: string[] = [];
  editor._tiptapEditor.state.doc.descendants(node => {
    if (node.type.name === "blockContainer" && node.firstChild?.type.name === "paragraph") result.push(`${String(node.attrs["id"])}=${node.firstChild.textContent}`);
  });
  return result;
}
export const settled = () => new Promise<void>(resolve => { setImmediate(resolve); });
