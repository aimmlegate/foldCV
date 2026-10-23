import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import type { Node } from "@tiptap/pm/model";
import { EditorState, TextSelection, type Transaction } from "@tiptap/pm/state";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import documentSchema from "../../../contracts/json-schema/rich_document_v2.schema.json" with { type: "json" };
import type { RichDocumentV2 } from "../src/contracts/generated/rich_document_v2";
import { parseJsonWire, type JsonWireNode } from "../src/contracts/lossless-json";
import { taggedSchema } from "../src/contracts/tagged-schema";
import { templateSchema } from "../src/rich/template-schema";
import { extractOperations, foldComposition, mergeAt, selectedBlocks, splitAt, type ExtractedOperation } from "../src/rich/v7-extraction";
import { projectTemplateDocument, type TemplateEditorBlock } from "../src/rich/v7-projection";
import { translateIntent, type V7Operation } from "../src/rich/v7-translation";

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
addFormats(ajv);
const documentShape = ajv.compile<RichDocumentV2>(taggedSchema(documentSchema));

function record(value: unknown): Record<string, unknown> {
  assert.ok(typeof value === "object" && value !== null && !Array.isArray(value));
  return Object.fromEntries(Object.entries(value));
}
const fixture = record(JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/address-maps.json", import.meta.url), "utf8")));
assert.ok(Array.isArray(fixture["cases"]));
const typingCase = record(fixture["cases"].map(record).find(value => value["name"] === "field-typing"));
assert.equal(typeof typingCase["baseWire"], "string");
const response = parseJsonWire(String(typingCase["baseWire"]));
function documentOf(wire: JsonWireNode): RichDocumentV2 {
  const value = wire.children.get("workspace")?.children.get("project")?.children.get("document")?.value;
  assert.ok(documentShape(value)); return value;
}

function docOf(blocks: TemplateEditorBlock[]): Node {
  const editor = BlockNoteEditor.create({ schema: templateSchema, initialContent: blocks });
  const doc = editor._tiptapEditor.state.doc;
  editor._tiptapEditor.destroy();
  return doc;
}
const paperDoc = docOf(projectTemplateDocument(documentOf(response)));
function caret(doc: Node, pos: number): EditorState { return EditorState.create({ doc, selection: TextSelection.create(doc, pos) }); }
function start(doc: Node, id: string): number {
  let found = -1;
  doc.descendants((node, pos) => { if (node.type.name === "blockContainer" && node.attrs["id"] === id) found = pos + 2; return found < 0; });
  assert.ok(found >= 0, id); return found;
}
function only(tr: Transaction): ExtractedOperation {
  const result = extractOperations(tr);
  assert.equal(result.kind, "operations", result.kind === "unsupported" ? result.reason : "");
  assert.ok(result.kind === "operations" && result.operations.length === 1);
  const [value] = result.operations; assert.ok(value); return value;
}
function refused(tr: Transaction, reason: RegExp): void {
  const result = extractOperations(tr);
  assert.ok(result.kind === "unsupported", "input must be refused"); assert.match(result.reason, reason);
}
function translated(value: ExtractedOperation): unknown {
  const result = translateIntent({ localId: "op-1", operation: value.operation, prior: value.prior }, { response, map: null, locals: new Map() });
  assert.equal(result.kind, "operation", result.kind === "conflict" ? result.reason : "");
  return result.kind === "operation" ? result.operation : null;
}
function replace(value: V7Operation) { assert.ok(value.kind === "replace_text"); return value; }

// block-paper-a: "By " + field("Shared title") + " / " + field("Journal North") + ".".
const a = start(paperDoc, "block-paper-a");

test("collapsed typing takes its side from the editor node that received it", () => {
  const cases: [number, number, string, unknown][] = [
    [a + 10, 9, "interior", { kind: "field", bindingId: "fragment-paper-a" }],
    [a + 16, 15, "before", { kind: "field", bindingId: "fragment-paper-a" }],
    [a + 4, 3, "after", { kind: "field", bindingId: "fragment-paper-a" }],
    [a + 17, 15, "after", { kind: "literal" }],
    [a + 3, 3, "before", { kind: "literal" }],
    [a + 1, 1, "interior", { kind: "literal" }],
    [a, 0, "after", { kind: "literal" }],
  ];
  for (const [pos, offset, side, target] of cases) {
    const value = only(caret(paperDoc, pos).tr.insertText("X", pos));
    const operation = replace(value.operation);
    assert.deepEqual([operation.start, operation.end, operation.text, operation.side], [offset, offset, "X", side], `pos ${pos - a}`);
    assert.equal(value.prior.values().next().value, "By Shared title / Journal North.");
    assert.deepEqual(record(record(translated(value))["range"])["insertionTarget"], target, `pos ${pos - a}`);
  }
});

test("an emptied field keeps an anchor side and refuses structure-only removal", () => {
  const document = documentOf(response), block = document.regions[2]?.blocks[1];
  assert.ok(block && block.type === "paragraph");
  const field = block.content[0]; assert.ok(field && field.type === "fact_field"); field.text = "";
  const doc = docOf(projectTemplateDocument(document)), b = start(doc, "block-paper-b");
  const operation = replace(only(caret(doc, b + 1).tr.insertText("New", b + 1)).operation);
  assert.deepEqual([operation.start, operation.side, operation.container.blockId], [0, "anchor", "block-paper-b"]);
  refused(caret(doc, b).tr.delete(b, b + 2), /structure-only/);
});

test("deletion and range replacement leave ownership to Python", () => {
  const removed = replace(only(caret(paperDoc, a).tr.delete(a + 10, a + 12)).operation);
  assert.deepEqual([removed.start, removed.end, removed.text, removed.side], [9, 11, "", null]);
  const crossing = replace(only(caret(paperDoc, a).tr.insertText("Z", a + 1, a + 10)).operation);
  assert.deepEqual([crossing.start, crossing.end, crossing.text, crossing.side], [1, 9, "Z", null]);
  const bold = paperDoc.type.schema.marks["bold"]?.create(); assert.ok(bold);
  const styled = replace(only(caret(paperDoc, a).tr.replaceWith(a + 1, a + 1, paperDoc.type.schema.text("B", [bold]))).operation);
  assert.equal(styled.styles.bold, true);
  const hardBreak = paperDoc.type.schema.nodes["hardBreak"]?.create(); assert.ok(hardBreak);
  assert.equal(replace(only(caret(paperDoc, a).tr.replaceWith(a + 1, a + 1, hardBreak)).operation).text, "\n");
});

test("marks become uniform set_marks runs per container", () => {
  const schema = paperDoc.type.schema, bold = schema.marks["bold"]?.create(), italic = schema.marks["italic"]?.create();
  assert.ok(bold && italic);
  const italicDoc = caret(paperDoc, a).tr.addMark(a + 1, a + 2, italic).doc;
  const result = extractOperations(caret(italicDoc, a).tr.addMark(a + 1, a + 10, bold));
  assert.ok(result.kind === "operations");
  assert.deepEqual(result.operations.map(({ operation }) => operation.kind === "set_marks"
    ? [operation.start, operation.end, operation.styles.bold, operation.styles.italic] : null), [[1, 2, true, true], [2, 9, true, false]]);
  const color = schema.marks["textColor"]?.create({ stringValue: "red" }); assert.ok(color);
  const colored = only(caret(paperDoc, a).tr.addMark(a, a + 2, color)).operation;
  assert.ok(colored.kind === "set_marks"); assert.match(colored.styles.textColor ?? "", /^#[0-9a-f]{6}$/);
  const both = extractOperations(caret(paperDoc, a).tr.addMark(a + 30, start(paperDoc, "block-paper-b") + 3, bold));
  assert.ok(both.kind === "operations");
  assert.deepEqual(both.operations.map(({ operation }) => operation.kind === "set_marks" ? operation.container.blockId : null), ["block-paper-a", "block-paper-b"]);
  const link = schema.marks["link"]?.create({ href: "https://example.test" }); assert.ok(link);
  refused(caret(paperDoc, a).tr.addMark(a, a + 2, link), /unsupported mark link/);
});

const structureDoc = docOf([{ id: "main", type: "region", props: { role: "main" }, children: [
  { id: "p1", type: "paragraph", content: "Alpha", children: [{ id: "c1", type: "paragraph", content: "Child" }] },
  { id: "p2", type: "paragraph", content: "Beta" },
  { id: "p4", type: "bulletListItem", content: "Delta", children: [{ id: "c2", type: "paragraph", content: "Kept" }] },
  { id: "s1", type: "section", content: "Section" },
  { id: "p3", type: "paragraph", content: [{ type: "link", href: "https://example.test", content: "Link" }] },
  { id: "p5", type: "paragraph", content: [
    { type: "templateField", props: { bindingId: "f1", occurrenceId: "o1", recordId: "r1", fieldKey: "a", cellId: "", complete: true }, content: "One" },
    { type: "templateField", props: { bindingId: "f2", occurrenceId: "o2", recordId: "r1", fieldKey: "b", cellId: "", complete: false }, content: "Two" }] },
] }]);
function blocks(doc: Node): string[] {
  const result: string[] = [];
  doc.descendants(node => {
    if (node.type.name === "blockContainer" && node.firstChild?.type.name !== "region")
      result.push(`${String(node.attrs["id"])}:${node.firstChild?.textContent ?? ""}:${node.childCount > 1 ? "children" : "leaf"}`);
  });
  return result;
}
function applied(value: ReturnType<typeof splitAt>) {
  assert.ok("transaction" in value, "reason" in value ? value.reason : "");
  return value;
}

test("Enter splits like Python: the right half is a new sibling and children stay left", () => {
  const p1 = start(structureDoc, "p1");
  const split = applied(splitAt(caret(structureDoc, p1 + 2), "local-1"));
  assert.deepEqual(split.operation.operation, { kind: "split_block", container: { blockId: "p1", kind: "content", cellId: null }, offset: 2, created: "local-1" });
  assert.deepEqual(blocks(split.transaction.doc).slice(0, 3), ["p1:Al:children", "c1:Child:leaf", "local-1:pha:leaf"]);
  assert.equal(split.transaction.selection.from, start(split.transaction.doc, "local-1"));
  assert.equal(only(split.transaction), split.operation);
  const paper = applied(splitAt(caret(paperDoc, a + 10), "local-2"));
  const operation = record(translated(paper.operation));
  assert.deepEqual([operation["kind"], operation["blockId"], operation["offset"]], ["split_block", "block-paper-a", 9]);
  assert.deepEqual(blocks(paper.transaction.doc).slice(0, 2), ["block-paper-a:By Shared:leaf", "local-2: title / Journal North.:leaf"]);
  const section = splitAt(caret(structureDoc, start(structureDoc, "s1") + 2), "local-x");
  assert.ok("reason" in section); assert.match(section.reason, /section blocks keep/);
});

test("Backspace and Delete merge adjacent text siblings only", () => {
  const p4 = start(structureDoc, "p4"), p2 = start(structureDoc, "p2");
  const backward = applied(mergeAt(caret(structureDoc, p4), "backward"));
  const forward = applied(mergeAt(caret(structureDoc, p2 + 4), "forward"));
  for (const value of [backward, forward]) {
    assert.deepEqual(value.operation.operation, { kind: "merge_blocks", leading: { blockId: "p2", kind: "content", cellId: null },
      trailing: { blockId: "p4", kind: "content", cellId: null } });
    assert.deepEqual([...value.operation.prior.values()], ["Beta", "Delta"]);
    assert.deepEqual(blocks(value.transaction.doc).slice(2, 5), ["p2:BetaDelta:children", "c2:Kept:leaf", "s1:Section:leaf"]);
    assert.equal(value.transaction.selection.from, p2 + 4);
  }
  const reason = (value: ReturnType<typeof mergeAt>) => "reason" in value ? value.reason : "merged";
  assert.match(reason(mergeAt(caret(structureDoc, p2), "backward")), /leading block has children/);
  assert.match(reason(mergeAt(caret(structureDoc, start(structureDoc, "p3")), "backward")), /only text blocks merge/);
  assert.match(reason(mergeAt(caret(structureDoc, start(structureDoc, "c1")), "backward")), /no adjacent sibling/);
  assert.match(reason(mergeAt(caret(structureDoc, p2 + 1), "backward")), /block edge/);
  assert.match(reason(mergeAt(caret(structureDoc, start(structureDoc, "s1")), "backward")), /section blocks keep/);
  // Mid-text Backspace in a section is ordinary deletion, not a refused merge.
  assert.match(reason(mergeAt(caret(structureDoc, start(structureDoc, "s1") + 2), "backward")), /block edge/);
  const paper = applied(mergeAt(caret(paperDoc, start(paperDoc, "block-paper-b")), "backward"));
  const merged = record(translated(paper.operation));
  assert.deepEqual([merged["kind"], merged["leadingId"], merged["trailingId"]], ["merge_blocks", "block-paper-a", "block-paper-b"]);
});

test("input Python cannot address is refused before it reaches the queue", () => {
  const p3 = start(structureDoc, "p3"), p5 = start(structureDoc, "p5");
  refused(caret(structureDoc, p3 + 2).tr.insertText("x", p3 + 2), /inside a link/);
  // Between two adjacent fields there is no literal leaf to receive the text.
  refused(caret(structureDoc, p5 + 5).tr.insertText("x", p5 + 5), /two non-literal/);
  refused(caret(structureDoc, p5 + 7).tr.insertText("x", p5 + 7), /incomplete field/);
  refused(caret(paperDoc, a).tr.delete(a + 5, start(paperDoc, "block-paper-b") + 3), /several containers/);
  refused(caret(paperDoc, a).tr.setNodeMarkup(a - 1, undefined, { textAlignment: "center" }), /structural editor step/);
  const field = paperDoc.type.schema.nodes["templateField"]?.create({ bindingId: "f9", complete: true }, paperDoc.type.schema.text("New"));
  assert.ok(field);
  refused(caret(paperDoc, a).tr.insert(a + 1, field), /structured input/);
});

test("a composition becomes one replacement at composition end", () => {
  const prior = (text: string) => new Map([['["block-paper-a","content",null]', text]]);
  const container = { blockId: "block-paper-a", kind: "content" as const, cellId: null };
  const styles = { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" };
  const updates: ExtractedOperation[] = [
    { operation: { kind: "replace_text", container, start: 5, end: 5, text: "k", styles, side: "interior" }, prior: prior("By Shared") },
    { operation: { kind: "replace_text", container, start: 5, end: 6, text: "ka", styles, side: null }, prior: prior("By Shkared") },
    { operation: { kind: "replace_text", container, start: 5, end: 7, text: "カ", styles, side: null }, prior: prior("By Shkaared") },
  ];
  const [first, , last] = updates; assert.ok(first && last);
  const folded = foldComposition(updates);
  assert.ok("operation" in folded);
  assert.deepEqual(folded.operation, { ...first.operation, text: "カ" });
  assert.deepEqual(foldComposition([first, last]), { reason: "composition left its container" });
});

test("composition beside repeated text keeps the actual insertion range", () => {
  const doc = docOf([{ id: "repeated", type: "paragraph", content: "ああ" }]), pos = start(doc, "repeated") + 1;
  const update = only(caret(doc, pos).tr.insertText("あ", pos)), folded = foldComposition([update]);
  assert.ok("operation" in folded);
  assert.deepEqual(folded.operation, update.operation);
  assert.equal(replace(folded.operation).start, 1);
});

for (const text of ["あ", "😀"]) test(`repeated composition updates retain the addressed UTF-16 range (${text})`, () => {
  const doc = docOf([{ id: "repeated", type: "paragraph", content: text + text }]);
  const pos = start(doc, "repeated") + text.length;
  const first = caret(doc, pos).tr.insertText(text, pos);
  const second = caret(first.doc, pos).tr.insertText("candidate", pos, pos + text.length);
  const last = caret(second.doc, pos).tr.insertText(text, pos, pos + "candidate".length);
  const updates = [only(first), only(second), only(last)], folded = foldComposition(updates);
  assert.ok("operation" in folded);
  const operation = replace(folded.operation);
  assert.deepEqual([operation.start, operation.end, operation.text], [text.length, text.length, text]);
  const prior = [...folded.prior.values()][0]; assert.ok(prior);
  assert.equal(prior.slice(0, operation.start) + operation.text + prior.slice(operation.end), text.repeat(3));
});

test("whole sibling selection excludes an unselected final subtree", () => {
  const doc = docOf([{ id: "a", type: "paragraph", content: "First" },
    { id: "b", type: "paragraph", content: "Second", children: [{ id: "c", type: "paragraph", content: "Unselected detail" }] },
    { id: "d", type: "paragraph", content: "Next" }]);
  const selection = (end: number) => EditorState.create({ doc, selection: TextSelection.create(doc, start(doc, "a"), end) });
  assert.equal(selectedBlocks(selection(start(doc, "b") + "Second".length)), null);
  assert.deepEqual(selectedBlocks(selection(start(doc, "d"))), ["a", "b"], "the next sibling start covers the whole subtree");
});
