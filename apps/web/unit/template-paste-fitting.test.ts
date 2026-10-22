import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor, type PartialBlock } from "@blocknote/core";
import { Slice, type Node } from "@tiptap/pm/model";
import { EditorState, TextSelection } from "@tiptap/pm/state";
import { schema } from "../src/rich/editor-schema";
import { basicPastedSlice } from "../src/rich/basic-editing";
import { flattenPastedRegions } from "../src/rich/regions";

type Input = PartialBlock<typeof schema.blockSchema, typeof schema.inlineContentSchema, typeof schema.styleSchema>;

function document(blocks: Input[]): Node {
  const editor = BlockNoteEditor.create({ schema, initialContent: blocks });
  const result = editor._tiptapEditor.state.doc;
  editor._tiptapEditor.destroy();
  return result;
}

function point(doc: Node, id: string, offset: number): number {
  let result: number | null = null;
  doc.descendants((node, position) => {
    const identifier: unknown = node.attrs["id"];
    if (node.type.name === "blockContainer" && identifier === id) result = position + 2 + offset;
  });
  assert.notEqual(result, null);
  return result ?? -1;
}

function selected(doc: Node, from: string, start: number, to: string, end: number): Slice {
  return TextSelection.create(doc, point(doc, from, start), point(doc, to, end)).content();
}

function fit(doc: Node, slice: Slice, from: string, start: number, to = from, end = start): Node {
  const state = EditorState.create({ schema: doc.type.schema, doc,
    selection: TextSelection.create(doc, point(doc, from, start), point(doc, to, end)) });
  const local = Slice.fromJSON(doc.type.schema, slice.toJSON());
  const result = state.tr.replaceSelection(local).doc;
  result.check();
  return result;
}

function blocks(doc: Node) {
  const group = doc.firstChild;
  assert.equal(group?.type.name, "blockGroup");
  const result: { id: string | null; kind: string; text: string; childGroups: number }[] = [];
  group?.forEach(node => {
    const id: unknown = node.attrs["id"];
    assert.ok(id === null || typeof id === "string");
    assert.ok(node.firstChild);
    result.push({ id, kind: node.firstChild.type.name, text: node.firstChild.textContent,
      childGroups: node.childCount - 1 });
  });
  return result;
}

for (const first of ["paragraph", "bulletListItem", "numberedListItem"] as const) {
  test(`actual ${first} selection fits flat open text edges with exact marks`, () => {
    const source = document([{ id: "first", type: first,
      content: [{ type: "text", text: "FIRST", styles: { bold: true } }] },
    { id: "last", type: "paragraph", content: "LAST" }]);
    const slice = selected(source, "first", 1, "last", 3);
    assert.equal(slice.openStart, 3); assert.equal(slice.openEnd, 3);
    const target = document([{ id: "destination", type: "paragraph", content: "prefixsuffix" }]);
    const result = fit(target, slice, "destination", 6);
    assert.deepEqual(blocks(result), [
      { id: "destination", kind: "paragraph", text: "prefixIRST", childGroups: 0 },
      { id: "last", kind: "paragraph", text: "LASsuffix", childGroups: 0 },
    ]);
    const firstContent = result.firstChild?.firstChild?.firstChild;
    assert.equal(firstContent?.childCount, 2);
    assert.equal(firstContent?.child(0).textContent, "prefix");
    assert.equal(firstContent?.child(0).marks.length, 0);
    assert.equal(firstContent?.child(1).textContent, "IRST");
    assert.deepEqual(firstContent?.child(1).marks.map(mark => mark.type.name), ["bold"]);
  });
}

test("actual custom open heading nests and has no flat slice equivalent", () => {
  const source = document([{ id: "first", type: "heading", props: { level: 2 }, content: "FIRST" },
    { id: "last", type: "paragraph", content: "LAST" }]);
  const slice = selected(source, "first", 1, "last", 3);
  assert.equal(slice.openStart, 3);
  const result = fit(document([{ id: "destination", type: "paragraph", content: "prefixsuffix" }]), slice, "destination", 6);
  assert.deepEqual(blocks(result), [{ id: "destination", kind: "paragraph", text: "prefix", childGroups: 1 }]);
  const nested = result.firstChild?.firstChild?.lastChild;
  assert.equal(nested?.type.name, "blockGroup");
  assert.equal(nested?.firstChild?.firstChild?.type.name, "heading");
  assert.equal(nested?.firstChild?.firstChild?.textContent, "IRST");
  assert.equal(nested?.lastChild?.firstChild?.textContent, "LASsuffix");
});

test("raw container-open depth two differs from actual selected wrapper depth three", () => {
  const source = document([{ id: "first", type: "heading", content: "FIRST" },
    { id: "last", type: "paragraph", content: "LAST" }]);
  assert.ok(source.firstChild);
  const raw = new Slice(source.firstChild.content, 2, 2);
  const target = document([{ id: "destination", type: "paragraph", content: "prefixsuffix" }]);
  assert.deepEqual(blocks(fit(target, raw, "destination", 6)), [
    { id: "destination", kind: "paragraph", text: "prefix", childGroups: 0 },
    { id: "first", kind: "heading", text: "FIRST", childGroups: 0 },
    { id: "last", kind: "paragraph", text: "LASTsuffix", childGroups: 0 },
  ]);
});

for (const boundary of ["middle", "start", "end", "full", "empty"] as const) {
  test(`actual closed heading and numbered paste at ${boundary} retains the fitted boundaries`, () => {
    const source = document([{ id: "heading", type: "heading", props: { level: 2, textAlignment: "right" }, content: "FIRST" },
      { id: "numbered", type: "numberedListItem", props: { start: 7 }, content: "LAST" }]);
    assert.ok(source.firstChild);
    const slice = new Slice(source.firstChild.content, 0, 0);
    const text = boundary === "empty" ? "" : "prefixsuffix";
    const offset = boundary === "middle" ? 6 : boundary === "end" ? text.length : 0;
    const end = boundary === "full" ? text.length : offset;
    const result = fit(document([{ id: "destination", type: "paragraph", content: text }]), slice, "destination", offset, "destination", end);
    const actual = blocks(result);
    const sourceRows = [
      { id: "heading", kind: "heading", text: "FIRST", childGroups: 0 },
      { id: "numbered", kind: "numberedListItem", text: "LAST", childGroups: 0 },
    ];
    const expected = boundary === "middle" ? [
      { id: "destination", kind: "paragraph", text: "prefix", childGroups: 0 }, ...sourceRows,
      { id: "destination", kind: "paragraph", text: "suffix", childGroups: 0 },
    ] : boundary === "start" ? [
      { id: "destination", kind: "paragraph", text: "", childGroups: 0 }, ...sourceRows,
      { id: "destination", kind: "paragraph", text, childGroups: 0 },
    ] : boundary === "end" ? [{ id: "destination", kind: "paragraph", text, childGroups: 0 }, ...sourceRows] : sourceRows;
    assert.deepEqual(actual, expected);
    const heading = result.firstChild?.content.content.find(node => node.firstChild?.type.name === "heading")?.firstChild;
    assert.ok(heading);
    const level: unknown = heading.attrs["level"], alignment: unknown = heading.attrs["textAlignment"];
    assert.equal(level, 2); assert.equal(alignment, "right");
    const numbered = result.firstChild?.lastChild?.firstChild?.type.name === "numberedListItem"
      ? result.firstChild.lastChild.firstChild : result.firstChild?.child(result.firstChild.childCount - 2).firstChild;
    assert.ok(numbered);
    const start: unknown = numbered.attrs["start"];
    assert.equal(start, 7);
  });
}

test("actual flat cross-block selection replaces only the intervening authored blocks", () => {
  const target = document([{ id: "left", type: "paragraph", content: "prefixOLD" },
    { id: "middle", type: "bulletListItem", content: "REMOVE" },
    { id: "right", type: "numberedListItem", content: "OLDsuffix" },
    { id: "untouched", type: "paragraph", content: "KEEP" }]);
  const source = document([{ id: "source", type: "paragraph", content: "NEW" }]);
  const result = fit(target, selected(source, "source", 0, "source", 3), "left", 6, "right", 3);
  assert.deepEqual(blocks(result), [
    { id: "left", kind: "paragraph", text: "prefixNEWsuffix", childGroups: 0 },
    { id: "untouched", kind: "paragraph", text: "KEEP", childGroups: 0 },
  ]);
});

test("restricted-node normalization precedes region flattening in the actual schema", () => {
  const source = document([{ id: "region", type: "region", props: { role: "main" },
    children: [{ id: "quote", type: "quote", content: "KEEP" }, { id: "empty", type: "paragraph", content: "" }] }]);
  assert.ok(source.firstChild);
  const raw = new Slice(source.firstChild.content, 0, 0);
  const normalized = basicPastedSlice(raw), flattened = flattenPastedRegions(normalized);
  assert.ok(flattened); assert.equal(flattened.openStart, 0); assert.equal(flattened.openEnd, 0);
  const result = fit(document([{ id: "destination", type: "paragraph", content: "" }]), flattened, "destination", 0);
  assert.deepEqual(blocks(result), [
    { id: "quote", kind: "paragraph", text: "KEEP", childGroups: 0 },
    { id: "empty", kind: "paragraph", text: "", childGroups: 0 },
  ]);
});
