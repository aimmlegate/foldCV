import assert from "node:assert/strict";
import { BlockNoteEditor } from "@blocknote/core";
import type { Node } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import type { TemplateProjectResponseV1 } from "../../src/contracts/generated/contracts";
import { templateSchema } from "../../src/rich/template-schema";
import { textPoint, textPosition } from "../../src/rich/v7-extraction";
import { projectTemplateDocument } from "../../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../../src/rich/v7-session";
import { projectClient, type Harness, type Traffic } from "./template-harness";

// A real editor session on the Python service, for the range and paste cases of the tester feedback of 2026-11-23.
function storage(): Storage {
  const values = new Map<string, string>();
  return { get length() { return values.size; }, clear: () => values.clear(), getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null, removeItem: key => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); } };
}
Object.assign(globalThis, { sessionStorage: storage(), localStorage: storage() });

export const TASK = "Implemented queue processing";
export type Opened = { session: TemplateEditorSession; editor: TemplateEditor; warnings: string[]; traffic: Traffic[]; reopen: () => Promise<Opened> };

export async function opened(value: Harness): Promise<Opened> {
  const warnings: string[] = [], traffic: Traffic[] = [];
  const connection = await projectClient(value, traffic);
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} }, 60_000);
  const response = session.queue.template.durable;
  assert.ok(response?.workspace.project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(response.workspace.project.document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor, response.workspace.project.document);
  await session.recoverDraft();
  const reopen = async () => { await session.navigateAway(); session.close(); return opened(value); };
  return { session, editor, warnings, traffic, reopen };
}

export type Part = Record<string, unknown>;
export type Shown = { id: string; parent: string; type: string; text: string; parts: Part[] };
export function shown(session: TemplateEditorSession): { response: TemplateProjectResponseV1; blocks: Shown[] } {
  const response = session.queue.template.durable, project = response.workspace.project;
  assert.ok(project);
  const blocks: Shown[] = [];
  const visit = (block: Record<string, unknown>, parent: string) => {
    const content = Array.isArray(block["content"]) ? block["content"] as Part[] : [];
    blocks.push({ id: String(block["id"]), parent, type: String(block["type"]), parts: content,
      text: content.map(part => typeof part["text"] === "string" ? part["text"]
        : Array.isArray(part["content"]) ? (part["content"] as Part[]).map(child => String(child["text"] ?? "")).join("") : "").join("") });
    for (const child of block["children"] as Record<string, unknown>[]) visit(child, String(block["id"]));
  };
  for (const region of project.document.regions) for (const block of region.blocks) visit(block as unknown as Record<string, unknown>, region.id);
  return { response, blocks };
}
export const facts = (session: TemplateEditorSession) => JSON.stringify(session.queue.template.durable.workspace.project?.facts.records);
export const fields = (block: Shown | undefined) => (block?.parts ?? []).filter(part => "cellId" in part);
export function find(blocks: Shown[], text: string): Shown {
  const block = blocks.find(value => value.text === text);
  assert.ok(block, text); return block;
}
export const texts = (session: TemplateEditorSession) => shown(session).blocks.map(block => block.text);

export function doc(editor: TemplateEditor): Node { return editor._tiptapEditor.state.doc; }
export function at(editor: TemplateEditor, id: string, offset: number): number {
  const value = textPosition(doc(editor), { container: { blockId: id, kind: "content", cellId: null }, offset });
  assert.ok(value !== null, id); return value;
}
export function select(editor: TemplateEditor, anchor: number, head = anchor): void {
  const tr = editor._tiptapEditor.state.tr; tr.setSelection(TextSelection.create(tr.doc, anchor, head)); editor._tiptapEditor.view.dispatch(tr);
}
export function selectText(editor: TemplateEditor, block: Shown): void { select(editor, at(editor, block.id, 0), at(editor, block.id, block.text.length)); }
/** The caret as a block and a text offset. */
export function caret(editor: TemplateEditor): [string, number] | null {
  const point = textPoint(doc(editor), editor._tiptapEditor.state.selection.head);
  return point && [point.container.blockId, point.offset];
}

/** A key through the session's key handler; when the handler passes it on, ProseMirror's own deletion runs, as in a browser. */
export function press(editor: TemplateEditor, session: TemplateEditorSession, key: "Backspace" | "Delete" | "Enter"): boolean {
  const view = editor._tiptapEditor.view;
  const event = { key, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, preventDefault: () => {} } as unknown as KeyboardEvent;
  const handled = session.plugin.props.handleKeyDown?.call(session.plugin, view, event) ?? false;
  if (handled || key === "Enter") return handled;
  const { from, to, empty } = view.state.selection;
  view.dispatch(empty ? key === "Backspace" ? view.state.tr.delete(from - 1, from) : view.state.tr.delete(from, from + 1)
    : view.state.tr.deleteRange(from, to));
  return false;
}
/** Typed text through the session's text input prop; when it passes the text on, ProseMirror inserts it, as in a browser. */
export function type(editor: TemplateEditor, session: TemplateEditorSession, text: string): boolean {
  const view = editor._tiptapEditor.view, { from, to } = view.state.selection;
  const handled = session.plugin.props.handleTextInput?.call(session.plugin, view, from, to, text, () => view.state.tr.insertText(text, from, to)) ?? false;
  if (!handled) view.dispatch(view.state.tr.insertText(text, from, to));
  return handled;
}
export const sent = (traffic: Traffic[], kind: string) => traffic.filter(entry => entry.wire.includes(`"${kind}"`)).length;
