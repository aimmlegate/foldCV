import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import { TextSelection } from "@tiptap/pm/state";
import { templateSchema } from "../src/rich/template-schema";
import { projectTemplateDocument } from "../src/rich/v7-projection";
import { TemplateEditorSession, type TemplateEditor } from "../src/rich/v7-session";
import { blockStyle, changedBy, selectedTextBlocks, styledKind } from "../src/rich/selection";
import { harness, projectClient, record, type Traffic } from "./support/template-harness";

/** Toolbar block styles through Python: one format_blocks request, one Undo step, nothing sent for no change. */
async function opened(scenario: string) {
  const value = await harness(scenario), traffic: Traffic[] = [], warnings: string[] = [];
  const connection = await projectClient(value, traffic);
  const session = new TemplateEditorSession(connection, { status: () => {}, warning: text => warnings.push(text), mode: () => {}, shown: () => {} }, 60_000);
  const project = session.queue.template.durable.workspace.project;
  assert.ok(project);
  const editor: TemplateEditor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(project.document) });
  editor._tiptapEditor.registerPlugin(session.plugin);
  session.bind(editor, project.document);
  await session.recoverDraft();
  return { value, traffic, warnings, session, editor };
}

function start(editor: TemplateEditor, id: string): number {
  let found = -1;
  editor._tiptapEditor.state.doc.descendants((node, pos) => { if (node.type.name === "blockContainer" && node.attrs["id"] === id) found = pos + 2; return found < 0; });
  assert.ok(found >= 0, id);
  return found;
}
function select(editor: TemplateEditor, anchor: number, head = anchor): void {
  const tr = editor._tiptapEditor.state.tr;
  tr.setSelection(TextSelection.create(tr.doc, anchor, head));
  editor._tiptapEditor.view.dispatch(tr);
}
function kinds(session: TemplateEditorSession): Map<string, string> {
  const result = new Map<string, string>();
  for (const region of session.queue.template.durable.workspace.project?.document.regions ?? [])
    for (const block of region.blocks) result.set(block.id, block.type === "heading" ? `heading:${String(block.props.level)}` : block.type);
  return result;
}
function formats(traffic: readonly Traffic[]): unknown[] {
  return traffic.filter(entry => entry.path.endsWith("/edits")).map(entry => {
    const [operation] = (record(record(JSON.parse(entry.wire))["preparation"])["operations"] as unknown[]);
    const value = record(operation);
    return { kind: value["kind"], targets: (value["targets"] as unknown[]).map(target => record(target)["blockId"]), patch: value["patch"] };
  });
}

test("a list button formats every selected block in one request and one Undo, and toggles back", async () => {
  const { value, traffic, warnings, session, editor } = await opened("joined");
  try {
    select(editor, start(editor, "block-paper-a"), start(editor, "block-paper-b") + 3);
    assert.deepEqual(selectedTextBlocks(editor._tiptapEditor.state).map(block => block.id), ["block-paper-a", "block-paper-b"]);
    await session.format("numbered");
    assert.deepEqual(formats(traffic), [{ kind: "format_blocks", targets: ["block-paper-a", "block-paper-b"],
      patch: { blockKind: { type: "numbered_list", start: null } } }]);
    assert.equal(kinds(session).get("block-paper-a"), "numbered_list");
    assert.equal(kinds(session).get("block-paper-b"), "numbered_list");
    assert.equal(editor.getBlock("block-paper-a")?.type, "numberedListItem", "the editor shows Python's result");

    await session.navigate("undo");
    assert.equal(kinds(session).get("block-paper-a"), "paragraph");
    assert.equal(kinds(session).get("block-paper-b"), "paragraph", "one Undo reverts both blocks");
    assert.equal(session.canUndo, false);
    await session.navigate("redo");
    assert.equal(kinds(session).get("block-paper-b"), "numbered_list");

    // Every selected block is already that list: the same button makes them paragraphs again.
    select(editor, start(editor, "block-paper-a"), start(editor, "block-paper-b") + 3);
    await session.format("numbered");
    assert.equal(kinds(session).get("block-paper-a"), "paragraph");
    assert.equal(kinds(session).get("block-paper-b"), "paragraph");
    assert.deepEqual(warnings, []);
  } finally { session.close(); await value.close(); }
});

test("the style select changes only the caret block and sends nothing when the style is already set", async () => {
  const { value, traffic, warnings, session, editor } = await opened("joined");
  try {
    select(editor, start(editor, "block-paper-b") + 2);
    await session.format("h3");
    assert.equal(kinds(session).get("block-paper-b"), "heading:3");
    assert.equal(kinds(session).get("block-paper-a"), "paragraph");
    select(editor, start(editor, "block-paper-b") + 2);
    assert.equal(blockStyle(session.textBlocks()[0]), "h3");
    await session.format("h3");
    assert.equal(traffic.filter(entry => entry.path.endsWith("/edits")).length, 1, "no request for an unchanged style");
    await session.format("p");
    assert.equal(kinds(session).get("block-paper-b"), "paragraph");
    // A whole-block selection that ends at the next block's start does not reach that block.
    select(editor, start(editor, "block-paper-a"), start(editor, "block-paper-b"));
    assert.deepEqual(session.textBlocks().map(block => block.id), ["block-paper-a"]);
    assert.deepEqual(warnings, []);
  } finally { session.close(); await value.close(); }
});

test("toolbar kinds: lists toggle only when every block has the list; headings keep their level", () => {
  const paragraph = { id: "a", type: "paragraph" as const, level: null }, bullet = { id: "b", type: "bullet_list" as const, level: null };
  const heading = { id: "c", type: "heading" as const, level: 1 };
  assert.deepEqual(styledKind("list", [bullet, paragraph]), { type: "bullet_list" });
  assert.deepEqual(styledKind("list", [bullet]), { type: "paragraph" });
  assert.deepEqual(styledKind("numbered", []), { type: "numbered_list", start: null });
  assert.deepEqual(changedBy({ type: "heading", level: 2 }, [paragraph, heading, { ...heading, id: "d", level: 2 }]), ["a", "c"]);
  assert.deepEqual(changedBy({ type: "paragraph" }, [paragraph, bullet]), ["b"]);
  assert.equal(blockStyle(heading), "h2", "a level 1 section heading reads as «Заголовок»");
  assert.equal(blockStyle(undefined), "p");
});
