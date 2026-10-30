import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import type { Node } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { disabledExtensions, templateSchema } from "../src/rich/template-schema";
import { selectedBlocks, textPosition } from "../src/rich/v7-extraction";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { templateSheet } from "../src/rich/v7-presentation";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { projectClient, harness, type Harness, type Traffic } from "./support/template-harness";

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
  // Reopen: a clean detach, then a new writer session reads only the durable record.
  const reopen = async () => { await session.navigateAway(); session.close(); return opened(value); };
  return { session, editor, warnings, reopen };
}

type Part = Record<string, unknown>;
type Shown = { id: string; parent: string; type: string; text: string; parts: Part[] };
async function shown(session: TemplateEditorSession): Promise<{ response: TemplateProjectResponseV1; blocks: Shown[] }> {
  const response = session.queue.template.durable, project = response?.workspace.project;
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

test("E08: a bound link's URL edit changes only its URL cell and target, with its own Undo and Redo", async () => {
  const value = await harness("bound");
  const { session, editor, warnings } = await opened(value);
  try {
    const state = async () => {
      const { response, blocks } = await shown(session);
      const block = blocks.find(item => item.parts.some(part => part["type"] === "bound_link"));
      assert.ok(block);
      const link = block.parts.find(part => part["type"] === "bound_link") ?? {};
      const label = (link["content"] as Part[]).map(part => String(part["text"])).join("");
      const cells = response.workspace.project?.facts.extensions.find(record => record.id === "paper-a")?.cells ?? [];
      // The compact save keeps Python's editor plan: the link is live only for a web or mail address.
      const plan = response.presentation?.editor?.blocks[block.id];
      assert.ok(plan, "the editor plan follows each compact save");
      return { block, href: link["href"], label, live: (plan.links ?? []).length === 1,
        cells: new Map(cells.map(cell => [cell.fieldKey, cell.rawInput])) };
    };
    const before = await state();
    assert.deepEqual([before.href, before.label], ["https://example.test/a", "Shared title"]);
    select(editor, textStart(editor, "block-paper-b"));
    assert.equal(session.linkAtCaret(), null, "no link outside a bound link");
    select(editor, at(editor, before.block.id, 3));
    const target = session.linkAtCaret();
    assert.ok(target);
    assert.deepEqual([target.blockId, target.href], [before.block.id, "https://example.test/a"]);
    await session.linkTarget(target, "example.test/no-scheme");
    const plain = await state();
    assert.deepEqual([plain.href, plain.live], ["example.test/no-scheme", false]);
    const again = session.linkAtCaret() ?? target;
    await session.linkTarget(again, "https://example.test/revised");
    const after = await state();
    assert.deepEqual([after.href, after.label, after.live], ["https://example.test/revised", "Shared title", true]);
    assert.equal(after.cells.get("url"), "https://example.test/revised");
    assert.deepEqual([...after.cells].filter(([key]) => key !== "url"), [...before.cells].filter(([key]) => key !== "url"));
    await session.navigate("undo");
    assert.equal((await state()).href, "example.test/no-scheme");
    await session.navigate("undo");
    const undone = await state();
    assert.deepEqual([undone.href, undone.label, undone.cells.get("url"), undone.live],
      ["https://example.test/a", "Shared title", "https://example.test/a", true]);
    await session.navigate("redo");
    assert.equal((await state()).href, "example.test/no-scheme");
    assert.deepEqual(warnings, []);
  } finally { session.close(); await value.close(); }
});

test("B07/G02: lines inside one item move that item; a selection that crosses items is refused", async () => {
  const value = await harness("e04");
  const { session, editor, warnings } = await opened(value);
  try {
    let blocks = (await shown(session)).blocks;
    const children = (id: string) => blocks.filter(block => block.parent === id);
    const order = (ids: string[]) => blocks.filter(block => ids.includes(block.id)).map(block => block.id);
    const [first, second] = blocks.filter(block => block.type === "section" && children(block.id).length > 1);
    assert.ok(first && second);
    const lines = children(second.id), last = lines[lines.length - 1];
    assert.ok(lines[0] && last);
    // Every line of the second job, as Shift+Down or Shift+click selects them.
    select(editor, at(editor, lines[0].id, 0), at(editor, last.id, last.text.length));
    await session.move("up");
    blocks = (await shown(session)).blocks;
    assert.deepEqual(order([first.id, second.id]), [second.id, first.id]);
    assert.deepEqual(children(second.id).map(block => block.id), lines.map(block => block.id), "the item keeps its lines");
    await session.navigate("undo");
    blocks = (await shown(session)).blocks;
    assert.deepEqual(order([first.id, second.id]), [first.id, second.id]);
    assert.deepEqual(warnings, []);
    // The section line is hidden, so two visible lines of one item move that item and keep its lines.
    const partial = children(first.id);
    assert.ok(partial[0] && partial[1] && partial.length > 1);
    select(editor, at(editor, partial[0].id, 0), at(editor, partial[1].id, partial[1].text.length));
    await session.move("down");
    blocks = (await shown(session)).blocks;
    assert.deepEqual(order([first.id, second.id]), [second.id, first.id]);
    assert.deepEqual(children(first.id).map(block => block.id), partial.map(block => block.id), "a partial selection keeps the item's lines");
    await session.navigate("undo");
    blocks = (await shown(session)).blocks;
    assert.deepEqual(order([first.id, second.id]), [first.id, second.id]);
    // One selected line stays a line move. The item does not jump.
    const line = children(first.id)[0];
    assert.ok(line && line.text.length > 0);
    const inside = children(first.id).map(block => block.id);
    select(editor, at(editor, line.id, 0), at(editor, line.id, line.text.length));
    await session.move("down");
    blocks = (await shown(session)).blocks;
    assert.deepEqual(order([first.id, second.id]), [first.id, second.id], "one line does not move the item");
    assert.equal(warnings.length, 0);
    if (children(first.id).map(block => block.id).join() !== inside.join()) {
      await session.navigate("undo");
      blocks = (await shown(session)).blocks;
    }
    // Lines from two items are not one item: one warning, and nothing moves.
    const tail = partial[partial.length - 1], head = children(second.id)[0];
    assert.ok(tail && head);
    select(editor, at(editor, tail.id, 0), at(editor, head.id, head.text.length));
    await session.move("down");
    assert.deepEqual((await shown(session)).blocks.map(block => block.id), blocks.map(block => block.id));
    assert.equal(warnings.length, 1);
    // Review 2026-10-26: the first item does not move above its section heading.
    const heading = blocks.find(block => block.parent === first.parent && block.type === "heading");
    assert.ok(heading && order([heading.id, first.id])[0] === heading.id);
    const opening = children(first.id), closing = opening[opening.length - 1];
    assert.ok(opening[0] && closing);
    select(editor, at(editor, opening[0].id, 0), at(editor, closing.id, closing.text.length));
    await session.move("up");
    assert.deepEqual((await shown(session)).blocks.map(block => block.id), blocks.map(block => block.id));
    assert.equal(warnings.length, 1);
  } finally { session.close(); await value.close(); }
});

const AWARD = "Example Labs Quality Award", PAPER = "Reliable Queues";
/** The work items of the second template, in order, with the employment record each one shows. */
function employers(response: TemplateProjectResponseV1, blocks: Shown[]): { section: Shown; record: string }[] {
  const records = response.workspace.project?.facts.records.filter(record => record.kind === "employment") ?? [];
  return blocks.filter(block => block.type === "section").flatMap(section => {
    const record = records.find(value => blocks.some(block => block.parent === section.id
      && fields(block).some(field => String(field.cellId).includes(value.id))));
    return record ? [{ section, record: record.id }] : [];
  });
}
function extensionTargets(response: TemplateProjectResponseV1, kind: string): Map<string, string> {
  const facts = response.workspace.project?.facts;
  assert.ok(facts);
  return new Map(facts.relations.filter(value => value.active && value.kind === kind).map(value => [value.subjectId, value.targetId]));
}

test("D03/CT08: moving the award into the second employer changes only its owner; the division keeps its subject", async () => {
  const value = await harness("publications");
  const { session, editor, warnings } = await opened(value);
  try {
    let { response, blocks } = await shown(session);
    const [a, b] = employers(response, blocks);
    const award = blocks.find(block => block.text === AWARD), division = blocks.find(block => block.text.startsWith("Division: "));
    assert.ok(a && b && award && division && award.parent === a.section.id && division.parent === a.section.id);
    const owned = extensionTargets(response, "owned_by"), extended = extensionTargets(response, "extension_of");
    const [awardRecord] = [...owned.keys()], [divisionRecord] = [...extended.keys()];
    assert.ok(awardRecord && divisionRecord);
    assert.equal(owned.get(awardRecord), a.record);
    assert.equal(extended.get(divisionRecord), a.record);

    select(editor, textStart(editor, award.id));
    await session.move("down");
    await session.move("down");
    ({ response, blocks } = await shown(session));
    assert.equal(blocks.find(block => block.id === award.id)?.parent, b.section.id);
    assert.equal(extensionTargets(response, "owned_by").get(awardRecord), b.record, "the second employer owns the award");
    assert.equal(extensionTargets(response, "extension_of").get(divisionRecord), a.record, "the division still extends the first");
    await session.navigate("undo");
    ({ response } = await shown(session));
    assert.equal(extensionTargets(response, "owned_by").get(awardRecord), a.record, "Undo restores the first owner");
    await session.navigate("redo");
    ({ response } = await shown(session));
    assert.equal(extensionTargets(response, "owned_by").get(awardRecord), b.record);

    // The division occurrence moves among the first employer's lines only; its subject is fixed.
    const before = blocks.find(block => block.id === division.id)?.parent;
    select(editor, textStart(editor, division.id));
    await session.move("down");
    await session.move("down");
    await session.move("down");
    ({ response, blocks } = await shown(session));
    assert.notEqual(blocks.find(block => block.id === division.id)?.parent, before, "the occurrence itself moves");
    assert.deepEqual(warnings, []);
    assert.equal(extensionTargets(response, "extension_of").get(divisionRecord), a.record, "the division's subject never moves");
  } finally { session.close(); await value.close(); }
});

/** A block's parts with the parts inside its links: a bound link keeps its label occurrence among its children. */
function deepParts(block: Shown): Part[] {
  return block.parts.flatMap(part => Array.isArray(part["content"]) ? [part, ...(part["content"] as Part[])] : [part]);
}
const deepText = (block: Shown): string => deepParts(block).map(part => typeof part["text"] === "string" ? part["text"] : "").join("");
const deepFields = (block: Shown) => deepParts(block).filter(part => "cellId" in part).map(part => ({ cellId: part["cellId"], occurrenceId: part["occurrenceId"] }));

test("E04/CT08: two equal paper titles keep distinct cells and occurrences; reordering them changes no fact", async () => {
  const value = await harness("publications");
  const { session, editor } = await opened(value);
  try {
    let { response, blocks } = await shown(session);
    const titles = () => blocks.filter(block => deepText(block) === PAPER);
    const [first, second] = titles();
    assert.ok(first && second, JSON.stringify(blocks.map(block => deepText(block))));
    const [firstField] = deepFields(first), [secondField] = deepFields(second);
    assert.ok(firstField && secondField);
    assert.notEqual(firstField.cellId, secondField.cellId, "equal titles, distinct cells");
    assert.notEqual(firstField.occurrenceId, secondField.occurrenceId, "equal titles, distinct occurrences");
    const facts = factsWire(response), items = () => titles().map(block => block.parent);
    const [firstItem, secondItem] = items();
    assert.ok(firstItem && secondItem && firstItem !== secondItem);
    // Both lines of the second paper select its item, which moves above the first; its title keeps its cell.
    const lines = blocks.filter(block => block.parent === secondItem), last = lines[lines.length - 1];
    assert.ok(lines.length === 2 && last);
    select(editor, textStart(editor, second.id), at(editor, last.id, deepText(last).length));
    await session.move("up");
    ({ response, blocks } = await shown(session));
    assert.deepEqual(items(), [secondItem, firstItem]);
    assert.equal(factsWire(response), facts, "a reorder changes no fact");
    assert.deepEqual(deepFields(titles()[0] ?? second), [secondField]);
    await session.navigate("undo");
    ({ response, blocks } = await shown(session));
    assert.deepEqual(items(), [firstItem, secondItem]);
  } finally { session.close(); await value.close(); }
});

test("N04/CT08: the mounted sheet reads the second template's columns, type and bullet from its recipe", async () => {
  const value = await harness("publications");
  const { session } = await opened(value);
  try {
    const { response } = await shown(session);
    const sheet = templateSheet(response);
    assert.ok(sheet);
    const variables = sheet.variables as Record<string, string>;
    assert.deepEqual([variables["--fcv-columns"], variables["--fcv-gap"], variables["--fcv-bullet"]],
      ["130pt 420pt", "10pt", JSON.stringify("–")]);
    const body = sheet.styles.get("body");
    assert.ok(body && sheet.css.includes(`[data-fcv-style="${body}"]`) && /font-size: 11pt/.test(sheet.css));
    assert.equal(sheet.logo, null);
  } finally { session.close(); await value.close(); }
});

test("no BlockNote input rule is left that the session would only refuse", () => {
  const editor = BlockNoteEditor.create({ schema: templateSchema, disableExtensions: disabledExtensions });
  assert.deepEqual([...editor.extensions].filter(([, extension]) => extension.inputRules?.length).map(([key]) => key), []);
});

test("an empty region offers no control without a saved operation", () => {
  const source = readFileSync(new URL("../src/rich/editor-schema.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /<button|addText/u);
});
