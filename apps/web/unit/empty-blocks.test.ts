import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import type { Node } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/contracts";
import { templateDictionary, templateSchema } from "../src/rich/template-schema";
import { textPoint, textPosition } from "../src/rich/v7-extraction";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { projectClient, harness, type Harness, type Traffic } from "./support/template-harness";

// F2 of the tester feedback of 2026-11-23: an empty block is never a dead end. Scenario e04 on the real Python service.
function storage(): Storage {
  const values = new Map<string, string>();
  return { get length() { return values.size; }, clear: () => values.clear(), getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null, removeItem: key => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); } };
}
Object.assign(globalThis, { sessionStorage: storage(), localStorage: storage() });

const TASK = "Implemented queue processing";
type Opened = { session: TemplateEditorSession; editor: TemplateEditor; warnings: string[]; traffic: Traffic[]; reopen: () => Promise<Opened> };

async function opened(value: Harness): Promise<Opened> {
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

type Part = Record<string, unknown>;
type Shown = { id: string; parent: string; type: string; text: string; parts: Part[] };
function shown(session: TemplateEditorSession): { response: TemplateProjectResponseV1; blocks: Shown[] } {
  const response = session.queue.template.durable, project = response.workspace.project;
  assert.ok(project);
  const blocks: Shown[] = [];
  const visit = (block: Record<string, unknown>, parent: string) => {
    const content = Array.isArray(block["content"]) ? block["content"] as Part[] : [];
    blocks.push({ id: String(block["id"]), parent, type: String(block["type"]), parts: content,
      text: content.map(part => typeof part["text"] === "string" ? part["text"] : "").join("") });
    for (const child of block["children"] as Record<string, unknown>[]) visit(child, String(block["id"]));
  };
  for (const region of project.document.regions) for (const block of region.blocks) visit(block as unknown as Record<string, unknown>, region.id);
  return { response, blocks };
}
const facts = (session: TemplateEditorSession) => JSON.stringify(session.queue.template.durable.workspace.project?.facts.records);
const fields = (block: Shown | undefined) => (block?.parts ?? []).filter(part => "cellId" in part);
function find(blocks: Shown[], text: string): Shown {
  const block = blocks.find(value => value.text === text);
  assert.ok(block, text); return block;
}

function doc(editor: TemplateEditor): Node { return editor._tiptapEditor.state.doc; }
function at(editor: TemplateEditor, id: string, offset: number): number {
  const value = textPosition(doc(editor), { container: { blockId: id, kind: "content", cellId: null }, offset });
  assert.ok(value !== null, id); return value;
}
function select(editor: TemplateEditor, anchor: number, head = anchor): void {
  const tr = editor._tiptapEditor.state.tr; tr.setSelection(TextSelection.create(tr.doc, anchor, head)); editor._tiptapEditor.view.dispatch(tr);
}
function selectText(editor: TemplateEditor, block: Shown): void { select(editor, at(editor, block.id, 0), at(editor, block.id, block.text.length)); }
/** The caret as a block and a text offset. */
function caret(editor: TemplateEditor): [string, number] | null {
  const point = textPoint(doc(editor), editor._tiptapEditor.state.selection.head);
  return point && [point.container.blockId, point.offset];
}

/** A key through the session's key handler; when the handler passes it on, ProseMirror's own deletion runs, as in a browser. */
function press(editor: TemplateEditor, session: TemplateEditorSession, key: "Backspace" | "Delete"): boolean {
  const view = editor._tiptapEditor.view;
  const event = { key, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, preventDefault: () => {} } as unknown as KeyboardEvent;
  const handled = session.plugin.props.handleKeyDown?.call(session.plugin, view, event) ?? false;
  if (handled) return true;
  const { from, to, empty } = view.state.selection;
  view.dispatch(empty ? key === "Backspace" ? view.state.tr.delete(from - 1, from) : view.state.tr.delete(from, from + 1)
    : view.state.tr.deleteSelection());
  return false;
}
/** Select the whole text of a block and delete it, then save. */
async function empty(opened: Opened, block: Shown): Promise<void> {
  selectText(opened.editor, block);
  assert.equal(press(opened.editor, opened.session, "Backspace"), false, "a text selection is text input");
  await opened.session.flush();
}
const removals = (traffic: Traffic[]) => traffic.filter(entry => entry.wire.includes("\"remove_occurrences\"")).length;

/** Steps of A1: section 1 keeps only "Example Labs", then its text goes. */
async function onlyEmptyEmployer(current: Opened): Promise<{ section: Shown; line: Shown }> {
  const { session, editor } = current;
  const { blocks } = shown(session), line = find(blocks, "Example Labs"), section = blocks.find(block => block.id === line.parent);
  assert.ok(section);
  const lines = blocks.filter(block => block.parent === section.id), last = lines.at(-1), second = lines[1];
  assert.ok(second && last && lines.length > 2);
  select(editor, at(editor, second.id, 0), at(editor, last.id, last.text.length));
  assert.equal(press(editor, session, "Backspace"), true);
  await session.keyed();
  assert.deepEqual(shown(session).blocks.filter(block => block.parent === section.id).map(block => block.id), [line.id]);
  await empty(current, line);
  return { section, line };
}

for (const key of ["Backspace", "Delete"] as const) {
  test(`F2 A1/A5: ${key} in the last empty line of a card removes the line and its section; heading, card 2 and facts stay`, async () => {
    const value = await harness("e04");
    const current = await opened(value);
    try {
      const { session, editor, warnings } = current;
      const heading = find(shown(session).blocks, "PROJECTS"), second = find(shown(session).blocks, "Second Works");
      const { section, line } = await onlyEmptyEmployer(current);
      const before = facts(session);
      assert.equal(press(editor, session, key), true);
      await session.keyed();
      const { blocks } = shown(session);
      assert.equal(blocks.some(block => block.id === line.id || block.id === section.id), false, "the line and its section are gone");
      assert.ok(blocks.some(block => block.id === heading.id) && blocks.some(block => block.id === second.parent));
      assert.equal(facts(session), before, "the facts are unchanged by the removal");
      assert.deepEqual(caret(editor), key === "Backspace" ? [heading.id, "PROJECTS".length] : [second.id, 0]);
      assert.deepEqual(warnings, []);
    } finally { current.session.close(); await value.close(); }
  });
}

test("F2 A2: Undo brings back the empty line and its section with their IDs; Redo and reopen show them removed", async () => {
  const value = await harness("e04");
  let current = await opened(value);
  try {
    const { section, line } = await onlyEmptyEmployer(current);
    press(current.editor, current.session, "Backspace");
    await current.session.keyed();
    await current.session.navigate("undo");
    let blocks = shown(current.session).blocks;
    const back = blocks.find(block => block.id === line.id);
    assert.equal(back?.parent, section.id);
    assert.equal(back.text, "");
    assert.ok(blocks.some(block => block.id === section.id));
    await current.session.navigate("redo");
    blocks = shown(current.session).blocks;
    assert.equal(blocks.some(block => block.id === line.id || block.id === section.id), false);
    current = await current.reopen();
    blocks = shown(current.session).blocks;
    assert.equal(blocks.some(block => block.id === line.id || block.id === section.id), false, "the reopened project shows them removed");
    assert.deepEqual(current.warnings, []);
  } finally { current.session.close(); await value.close(); }
});

test("F2 A3: an emptied first line of a card goes; its section and other lines stay; the caret is at the end of the heading", async () => {
  const value = await harness("e04");
  const current = await opened(value);
  try {
    const { session, editor, warnings } = current;
    const { blocks } = shown(session), line = find(blocks, "Example Labs"), heading = find(blocks, "PROJECTS");
    const others = blocks.filter(block => block.parent === line.parent && block.id !== line.id).map(block => block.id);
    await empty(current, line);
    assert.equal(press(editor, session, "Backspace"), true);
    await session.keyed();
    const after = shown(session).blocks;
    assert.equal(after.some(block => block.id === line.id), false);
    assert.deepEqual(after.filter(block => block.parent === line.parent).map(block => block.id), others);
    assert.deepEqual(caret(editor), [heading.id, "PROJECTS".length]);
    assert.deepEqual(warnings, []);
  } finally { current.session.close(); await value.close(); }
});

test("F2 A4: an emptied heading goes; both sections stay; the caret is at the start of the next shown text", async () => {
  const value = await harness("e04");
  const current = await opened(value);
  try {
    const { session, editor, warnings } = current;
    const { blocks } = shown(session), heading = find(blocks, "PROJECTS"), first = find(blocks, "Example Labs");
    const sections = blocks.filter(block => block.type === "section").map(block => block.id);
    await empty(current, heading);
    assert.equal(press(editor, session, "Backspace"), true);
    await session.keyed();
    const after = shown(session).blocks;
    assert.equal(after.some(block => block.id === heading.id), false);
    assert.deepEqual(after.filter(block => block.type === "section").map(block => block.id), sections);
    assert.deepEqual(caret(editor), [first.id, 0]);
    assert.deepEqual(warnings, []);
  } finally { current.session.close(); await value.close(); }
});

test("F2 A6: Backspace at the start of a line with text and no sibling before it does nothing and says nothing", async () => {
  const value = await harness("e04");
  const current = await opened(value);
  try {
    const { session, editor, warnings } = current;
    const before = JSON.stringify(shown(session).blocks), line = find(shown(session).blocks, "Example Labs");
    select(editor, at(editor, line.id, 0));
    assert.equal(press(editor, session, "Backspace"), true);
    await session.keyed();
    await session.flush();
    assert.equal(JSON.stringify(shown(session).blocks), before);
    assert.deepEqual(warnings, []);
  } finally { current.session.close(); await value.close(); }
});

test("F2 A7/A8: an emptied bullet goes with no merge; an emptied label goes with Delete and the next bullet keeps its type", async () => {
  const value = await harness("e04");
  const current = await opened(value);
  try {
    const { session, editor, warnings } = current;
    let blocks = shown(session).blocks;
    const [first, second] = blocks.filter(block => block.text === TASK);
    assert.ok(first && second);
    await empty(current, second);
    assert.equal(press(editor, session, "Backspace"), true);
    await session.keyed();
    blocks = shown(session).blocks;
    assert.equal(blocks.some(block => block.id === second.id), false);
    assert.equal(fields(blocks.find(block => block.id === first.id)).length, 1, "bullet 1 holds one field fragment");
    assert.deepEqual(caret(editor), [first.id, TASK.length]);
    const tasks = find(blocks, "Tasks:");
    await empty(current, tasks);
    assert.equal(press(editor, session, "Delete"), true);
    await session.keyed();
    blocks = shown(session).blocks;
    assert.equal(blocks.some(block => block.id === tasks.id), false);
    assert.equal(blocks.find(block => block.id === first.id)?.type, "bullet_list");
    assert.deepEqual(caret(editor), [first.id, 0]);
    assert.deepEqual(warnings, []);
  } finally { current.session.close(); await value.close(); }
});

test("F2 A9: an emptied line after the technology line goes; the caret passes over the technology line", async () => {
  const value = await harness("e04");
  const current = await opened(value);
  try {
    const { session, editor, warnings } = current;
    const blocks = shown(session).blocks, role = find(blocks, "Role: Backend Engineer"), dates = find(blocks, "03.2020–11.2023");
    await empty(current, role);
    assert.equal(press(editor, session, "Backspace"), true);
    await session.keyed();
    assert.equal(shown(session).blocks.some(block => block.id === role.id), false);
    assert.deepEqual(caret(editor), [dates.id, dates.text.length], "the caret is in a shown text block, not in \"Python\"");
    assert.deepEqual(warnings, []);
  } finally { current.session.close(); await value.close(); }
});

test("F2 A10: two Backspace keys in an empty block with no wait between them make one removal and no warning", async () => {
  const value = await harness("e04");
  const current = await opened(value);
  try {
    const { session, editor, warnings, traffic } = current;
    const line = find(shown(session).blocks, "Example Labs"), count = shown(session).blocks.length;
    await empty(current, line);
    assert.equal(press(editor, session, "Backspace"), true);
    assert.equal(press(editor, session, "Backspace"), true);
    assert.equal(press(editor, session, "Delete"), true);
    await session.keyed();
    assert.equal(removals(traffic), 1);
    assert.equal(shown(session).blocks.length, count - 1);
    assert.deepEqual(warnings, []);
  } finally { current.session.close(); await value.close(); }
});

test("F2 A11: the last text block of the document stays, empty, with the caret", async () => {
  const value = await harness("e04");
  const current = await opened(value);
  try {
    const { session, editor, warnings } = current;
    const project = session.queue.template.durable.workspace.project;
    assert.ok(project);
    const tops = project.document.regions.flatMap(region => region.blocks.map(block => block.id)), last = tops.at(-1);
    assert.ok(last);
    await session.removeBlocks(tops.slice(0, -1));
    const only = shown(session).blocks;
    assert.deepEqual(only.map(block => block.id), [last]);
    await empty(current, only[0] ?? find(only, ""));
    for (const key of ["Backspace", "Delete"] as const) {
      assert.equal(press(editor, session, key), true);
      await session.keyed();
    }
    assert.deepEqual(shown(session).blocks.map(block => [block.id, block.text]), [[last, ""]]);
    assert.deepEqual(caret(editor), [last, 0]);
    assert.deepEqual(warnings, []);
  } finally { current.session.close(); await value.close(); }
});

test("F2 point 8: an empty heading shows «Заголовок»; other blocks show no placeholder and none names commands", () => {
  const placeholders: Record<string, string | undefined> = templateDictionary.placeholders;
  assert.equal(placeholders["heading"], "Заголовок");
  for (const key of ["default", "bulletListItem", "numberedListItem", "checkListItem", "toggleListItem", "emptyDocument"])
    assert.ok(!placeholders[key], key);
  assert.ok(Object.values(placeholders).every(text => !text || !/\//u.test(text)));
});
