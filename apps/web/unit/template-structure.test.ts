import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import type { Node } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import { attachTemplateWriter } from "../src/background/connection";
import { DraftRepository, type LocalDraft } from "../src/background/drafts";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { templateProjectWire } from "../src/contracts/template-validate";
import { templateSchema } from "../src/rich/template-schema";
import { selectedBlocks, textPosition } from "../src/rich/v7-extraction";
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

const TASK = "Implemented queue processing.";
const RESULT = "Our team reduced median latency from 800 ms to 500 ms.";
type Opened = { session: TemplateEditorSession; editor: TemplateEditor; warnings: string[]; reopen: () => Promise<Opened> };

async function opened(value: Harness, detach = true): Promise<Opened> {
  const api = client(value, []), warnings: string[] = [];
  let rows: LocalDraft[] = [];
  const repository = new DraftRepository({ transact: work => { const next = work(rows); rows = next.rows; return Promise.resolve(next.result); },
    discardProject: () => { rows = []; return Promise.resolve(); } }, () => Promise.reject(new Error("unused")));
  if (detach) {
    const fixture = await api.templateRead(value.proof);
    await api.templateDetach({ schemaVersion: 2, proof: value.proof, canonicalRevision: fixture.writer.acknowledgedRevision,
      canonicalSha256: fixture.writer.acknowledgedSha256 ?? fixture.workspaceSha256, actionCursor: fixture.writer.acknowledgedCursor, touches: [] });
  }
  const connection = await attachTemplateWriter(value.project, api, repository);
  assert.ok(connection?.proof, connection?.error ?? "attach failed");
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} }, 60_000);
  const response = await templateProjectWire(session.writer.durable);
  assert.ok(response?.workspace.project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(response.workspace.project.document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor, response.workspace.project.document);
  // Reopen: a clean detach, then a new writer session reads only the durable record.
  const reopen = async () => { await session.writer.navigate(); session.close(); return opened(value, false); };
  return { session, editor, warnings, reopen };
}

type Part = Record<string, unknown>;
type Shown = { id: string; parent: string; type: string; text: string; parts: Part[] };
async function shown(session: TemplateEditorSession): Promise<{ response: TemplateProjectResponseV1; blocks: Shown[] }> {
  const response = await templateProjectWire(session.queue.template.durable), project = response?.workspace.project;
  assert.ok(response && project);
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
function fields(block: Shown): { cellId: unknown; occurrenceId: unknown }[] {
  return block.parts.filter(part => "cellId" in part).map(part => ({ cellId: part["cellId"], occurrenceId: part["occurrenceId"] }));
}
function unique(values: { cellId: unknown; occurrenceId: unknown }[]): { cellId: unknown; occurrenceId: unknown }[] {
  return [...new Map(values.map(value => [JSON.stringify(value), value])).values()];
}
function relations(response: TemplateProjectResponseV1): Map<string, string> {
  const facts = response.workspace.project?.facts;
  assert.ok(facts);
  return new Map(facts.relations.filter(value => value.active && value.kind === "owned_by").map(value => [value.subjectId, value.targetId]));
}
function factsWire(response: TemplateProjectResponseV1): string { return JSON.stringify(response.workspace.project?.facts.records); }

function doc(editor: TemplateEditor): Node { return editor._tiptapEditor.state.doc; }
function textStart(editor: TemplateEditor, id: string): number {
  let found = -1;
  doc(editor).descendants((node, pos) => { if (node.type.name === "blockContainer" && node.attrs["id"] === id) found = pos + 2; return found < 0; });
  assert.ok(found >= 0, id); return found;
}
/** The editor position after `offset` characters of a block's text, inside field nodes as typing would be. */
function at(editor: TemplateEditor, id: string, offset: number): number {
  const value = textPosition(doc(editor), { container: { blockId: id, kind: "content", cellId: null }, offset });
  assert.ok(value !== null, id); return value;
}
function select(editor: TemplateEditor, anchor: number, head = anchor): void {
  const tr = editor._tiptapEditor.state.tr; tr.setSelection(TextSelection.create(tr.doc, anchor, head)); editor._tiptapEditor.view.dispatch(tr);
}
/** From the first block's text start to the next sibling's text start: whole blocks, as Shift+Down selects them. */
function selectWhole(editor: TemplateEditor, first: string, next: string): void { select(editor, textStart(editor, first), textStart(editor, next)); }

test("E04: reorder, edit, split and merge the second identical task touch only its own cell", async () => {
  const value = await harness("e04");
  const { session, editor } = await opened(value);
  try {
    let { response, blocks } = await shown(session);
    const [first, second] = blocks.filter(block => block.text === TASK);
    assert.ok(first && second);
    const [firstField] = fields(first), [secondField] = fields(second);
    assert.ok(firstField && secondField);
    assert.notEqual(firstField.cellId, secondField.cellId, "identical wording, distinct cells");
    const facts = factsWire(response);

    select(editor, textStart(editor, second.id));
    await session.move("up");
    ({ response, blocks } = await shown(session));
    const order = () => blocks.filter(block => block.text === TASK).map(block => block.id);
    assert.deepEqual(order(), [second.id, first.id]);
    assert.equal(factsWire(response), facts, "a reorder changes no fact");
    await session.navigate("undo");
    ({ response, blocks } = await shown(session));
    assert.deepEqual(order(), [first.id, second.id]);
    await session.navigate("redo");
    ({ response, blocks } = await shown(session));
    assert.deepEqual(order(), [second.id, first.id]);

    // Typing at the end of the second task changes only its claim.
    const end = at(editor, second.id, TASK.length);
    select(editor, end);
    const typed = editor._tiptapEditor.state.tr.insertText(" Again", end); editor._tiptapEditor.view.dispatch(typed);
    await session.flush();
    ({ response, blocks } = await shown(session));
    const claims = new Map(response.workspace.project?.facts.records.filter(record => record.kind === "claim")
      .map(record => [record.id, (record as unknown as { value: { rawText: string } }).value.rawText]));
    const values = [...claims.values()].sort();
    assert.deepEqual(values, [RESULT, TASK, `${TASK} Again`].sort());

    // Split the edited task; both fragments keep its one occurrence and cell.
    select(editor, at(editor, second.id, "Implemented".length));
    assert.equal(session.enter(), true);
    await session.flush();
    ({ response, blocks } = await shown(session));
    const fragments = blocks.filter(block => fields(block).some(field => field.cellId === secondField.cellId));
    assert.deepEqual(fragments.map(block => block.text), ["Implemented", " queue processing. Again"]);
    assert.deepEqual(new Set(fragments.map(block => fields(block)[0]?.occurrenceId)), new Set([secondField.occurrenceId]));
    const right = fragments[1];
    assert.ok(right);
    await session.reproject();
    select(editor, textStart(editor, right.id));
    assert.equal(session.join("backward"), true);
    await session.flush();
    ({ response, blocks } = await shown(session));
    const merged = blocks.filter(block => fields(block).some(field => field.cellId === secondField.cellId));
    assert.deepEqual(merged.map(block => [block.id, block.text]), [[second.id, `${TASK} Again`]]);
    // One occurrence may stay in several adjacent parts after split and merge; its identity is what matters.
    assert.deepEqual(unique(fields(merged[0] ?? second)), [secondField]);
    assert.equal(fields(blocks.find(block => block.id === first.id) ?? first)[0]?.cellId, firstField.cellId);
  } finally { session.close(); await value.close(); }
});

test("E04: a complete block copy gets its own occurrence root; removing it keeps the fact; Undo, Redo and reopen keep identities", async () => {
  const value = await harness("e04");
  let current = await opened(value);
  try {
    const { session, editor } = current;
    let { response, blocks } = await shown(session);
    const tasks = blocks.filter(block => block.text === TASK), second = tasks[1];
    assert.ok(second);
    const [source] = fields(second), facts = factsWire(response);
    assert.ok(source);
    const after = blocks[blocks.indexOf(second) + 1];
    assert.ok(after);
    selectWhole(editor, second.id, after.id);
    assert.deepEqual(selectedBlocks(editor._tiptapEditor.state), [second.id]);
    const copied = session.copySelection();
    assert.ok(copied);
    await copied.done;
    select(editor, at(editor, second.id, TASK.length));
    await session.pasteFrom(copied, copied.text);
    ({ response, blocks } = await shown(session));
    const copies = blocks.filter(block => block.text === TASK);
    assert.equal(copies.length, 3, "the copy is a separate block, not concatenated text");
    const copy = blocks[blocks.findIndex(block => block.id === second.id) + 1];
    assert.ok(copy && copy.text === TASK && copy.parent === second.parent);
    const [copyField] = fields(copy);
    assert.equal(copyField?.cellId, source.cellId, "same claim cell");
    assert.notEqual(copyField?.occurrenceId, source.occurrenceId, "a separate occurrence root");
    assert.equal(factsWire(response), facts, "copying adds no fact");

    const next = blocks[blocks.indexOf(copy) + 1];
    assert.ok(next);
    await session.reproject();
    selectWhole(editor, copy.id, next.id);
    const removal = selectedBlocks(editor._tiptapEditor.state);
    assert.deepEqual(removal, [copy.id]);
    await session.removeBlocks(removal ?? []);
    ({ response, blocks } = await shown(session));
    assert.equal(blocks.filter(block => block.text === TASK).length, 2);
    assert.equal(factsWire(response), facts, "deleting the copy keeps the claim");

    await session.navigate("undo");
    ({ response, blocks } = await shown(session));
    assert.deepEqual(fields(blocks.find(block => block.id === copy.id) ?? second), [copyField], "Undo restores the exact copy identity");
    await session.navigate("redo");
    ({ blocks } = await shown(session));
    assert.equal(blocks.some(block => block.id === copy.id), false);
    await session.navigate("undo");
    current = await current.reopen();
    ({ blocks } = await shown(current.session));
    assert.deepEqual(fields(blocks.find(block => block.id === copy.id) ?? second), [copyField], "reopen keeps the copy identity");
    assert.deepEqual(fields(blocks.find(block => block.id === second.id) ?? copy), [source]);
  } finally { current.session.close(); await value.close(); }
});

test("E04: moving the result into the second employer changes only its owner; Undo restores the first", async () => {
  const value = await harness("e04");
  const { session, editor } = await opened(value);
  try {
    let { response, blocks } = await shown(session);
    const result = blocks.find(block => block.text === RESULT), sections = blocks.filter(block => block.type === "section");
    assert.ok(result && sections.length === 2);
    const [a, b] = sections;
    assert.ok(a && b && result.parent === a.id);
    const [cell] = fields(result);
    const claim = response.workspace.project?.facts.records.find(record => record.kind === "claim"
      && (record as unknown as { value: { rawText: string } }).value.rawText === RESULT);
    assert.ok(claim && cell);
    const employer = (section: Shown) => response.workspace.project?.facts.records.find(record => record.kind === "employment"
      && blocks.some(block => block.parent === section.id && fields(block).some(field => String(field.cellId).includes(record.id))))?.id;
    const ownerA = employer(a), ownerB = employer(b);
    assert.ok(ownerA && ownerB && ownerA !== ownerB);
    assert.equal(relations(response).get(claim.id), ownerA);

    select(editor, textStart(editor, result.id));
    await session.move("down");
    ({ response, blocks } = await shown(session));
    assert.notEqual(blocks.find(block => block.id === result.id)?.parent, a.id, "out of the first employer");
    assert.equal(relations(response).get(claim.id), ownerA, "no owner context: ownership is unchanged");
    select(editor, textStart(editor, result.id));
    await session.move("down");
    ({ response, blocks } = await shown(session));
    assert.equal(blocks.find(block => block.id === result.id)?.parent, b.id);
    assert.equal(relations(response).get(claim.id), ownerB, "the second employer owns it");
    assert.deepEqual(fields(blocks.find(block => block.id === result.id) ?? result), [cell]);

    await session.navigate("undo");
    ({ response, blocks } = await shown(session));
    assert.equal(relations(response).get(claim.id), ownerA, "Undo restores the first owner");
    await session.navigate("undo");
    ({ response, blocks } = await shown(session));
    assert.equal(blocks.find(block => block.id === result.id)?.parent, a.id);
    await session.navigate("redo");
    await session.navigate("redo");
    ({ response } = await shown(session));
    assert.equal(relations(response).get(claim.id), ownerB);
  } finally { session.close(); await value.close(); }
});

test("E04: copying only Engineer pastes literal text with citations and no field binding", async () => {
  const value = await harness("e04");
  const { session, editor } = await opened(value);
  try {
    let { response, blocks } = await shown(session);
    const role = blocks.find(block => block.text === "Role: Backend Engineer"), target = blocks.find(block => block.text === "2024–present");
    assert.ok(role && target);
    const facts = factsWire(response), from = "Role: Backend ".length;
    select(editor, at(editor, role.id, from), at(editor, role.id, from + "Engineer".length));
    const copied = session.copySelection();
    assert.ok(copied);
    assert.equal(copied.text, "Engineer");
    await copied.done;
    select(editor, at(editor, target.id, "2024–present".length));
    await session.pasteFrom(copied, copied.text);
    ({ response, blocks } = await shown(session));
    const pasted = blocks.find(block => block.id === target.id);
    assert.equal(pasted?.text, "2024–presentEngineer");
    const part = pasted?.parts.find(item => item["text"] === "Engineer");
    assert.ok(part, "the copied text stays one part");
    assert.equal("cellId" in part, false, "a partial field copy has no field binding");
    assert.ok(Array.isArray(part["citations"]) && part["citations"].length > 0, "it keeps its source citation");
    assert.equal(factsWire(response), facts, "no cell changes");
    assert.equal(blocks.find(block => block.id === role.id)?.text, "Role: Backend Engineer");
  } finally { session.close(); await value.close(); }
});

test("E04: merging the two task bullets keeps both distinct cells; Undo splits them back with their IDs", async () => {
  const value = await harness("e04");
  const { session, editor } = await opened(value);
  try {
    let { response, blocks } = await shown(session);
    const [first, second] = blocks.filter(block => block.text === TASK);
    assert.ok(first && second);
    const before = [...fields(first), ...fields(second)], facts = factsWire(response);
    select(editor, textStart(editor, second.id));
    assert.equal(session.join("backward"), true);
    await session.flush();
    ({ response, blocks } = await shown(session));
    const merged = blocks.find(block => block.id === first.id);
    assert.equal(merged?.text, TASK + TASK);
    assert.deepEqual(fields(merged ?? first), before, "both cells and occurrences remain");
    assert.equal(factsWire(response), facts);
    await session.navigate("undo");
    ({ blocks } = await shown(session));
    assert.deepEqual(blocks.filter(block => block.text === TASK).map(block => [block.id, fields(block)]),
      [[first.id, fields(first)], [second.id, fields(second)]]);
  } finally { session.close(); await value.close(); }
});

test("a section copy is refused by Python and pastes nothing; a cut of whole blocks waits for the capture", async () => {
  const value = await harness("e04");
  const { session, editor, warnings } = await opened(value);
  try {
    let { blocks } = await shown(session);
    const sections = blocks.filter(block => block.type === "section");
    const [a, b] = sections;
    assert.ok(a && b);
    // Sections hold children, which Python does not capture: the copy keeps plain text only.
    const first = blocks.find(block => block.parent === a.id), heading = blocks.find(block => block.type === "heading");
    assert.ok(first && heading);
    selectWhole(editor, a.id, b.id);
    const section = session.copySelection();
    assert.ok(section);
    assert.equal(await section.capture, null);
    const unchanged = JSON.stringify((await shown(session)).blocks);
    select(editor, at(editor, first.id, first.text.length));
    await session.pasteFrom(section, section.text);
    assert.equal(JSON.stringify((await shown(session)).blocks), unchanged, "several paragraphs of plain text are refused");
    assert.equal(warnings.length, 1);
    warnings.length = 0;
    const tasks = blocks.filter(block => block.text === TASK), second = tasks[1];
    assert.ok(second);
    const next = blocks[blocks.indexOf(second) + 1];
    assert.ok(next);
    selectWhole(editor, second.id, next.id);
    const cut = session.copySelection(true);
    assert.ok(cut);
    await cut.done;
    ({ blocks } = await shown(session));
    assert.equal(blocks.some(block => block.id === second.id), false, "cut removes the block after capture");
    await session.reproject();
    select(editor, at(editor, tasks[0]?.id ?? "", TASK.length));
    await session.pasteFrom(cut, cut.text);
    ({ blocks } = await shown(session));
    assert.equal(blocks.filter(block => block.text === TASK).length, 2, "the cut block pastes back");
    assert.equal(warnings.length, 0, warnings.join("\n"));
  } finally { session.close(); await value.close(); }
});

test("whole-block selection is read in text offsets, so a caret inside a block's first field still counts as its start", async () => {
  const value = await harness("e04");
  const { session, editor } = await opened(value);
  try {
    const { blocks } = await shown(session);
    const tasks = blocks.filter(block => block.text === TASK), second = tasks[1];
    assert.ok(second);
    const next = blocks[blocks.indexOf(second) + 1];
    assert.ok(next);
    // Inside the field node, one position after the text block start: the place Cmd+Left leaves the caret.
    select(editor, textStart(editor, second.id) + 1, textStart(editor, next.id));
    assert.deepEqual(selectedBlocks(editor._tiptapEditor.state), [second.id]);
    select(editor, textStart(editor, second.id) + 1, at(editor, next.id, 3));
    assert.equal(selectedBlocks(editor._tiptapEditor.state), null, "a partial next block is text, not structure");
  } finally { session.close(); await value.close(); }
});

test("plain text from outside the project pastes into one block as typing", async () => {
  const value = await harness("e04");
  const { session, editor, warnings } = await opened(value);
  try {
    const target = (await shown(session)).blocks.find(block => block.text === "2024–present");
    assert.ok(target);
    select(editor, at(editor, target.id, target.text.length));
    await session.pasteFrom(null, " (remote)");
    await session.flush();
    const { blocks } = await shown(session);
    assert.equal(blocks.find(block => block.id === target.id)?.text, "2024–present (remote)");
    assert.equal(warnings.length, 0);
  } finally { session.close(); await value.close(); }
});
