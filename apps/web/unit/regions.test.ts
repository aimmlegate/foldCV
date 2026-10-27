import assert from "node:assert/strict";
import test from "node:test";
import { BlockNoteEditor, BlockNoteSchema, createBlockSpec, defaultBlockSpecs } from "@blocknote/core";
import { projectRegionChildren } from "../src/workbench/editor/regions";
import { SessionHistory } from "../src/rich/history";

test("real editor region moves survive shared undo and redo through authored empty regions", () => {
  const region = createBlockSpec({ type: "region", propSchema: {}, content: "none" }, {
    render: () => { throw new Error("Headless test"); },
  })();
  const schema = BlockNoteSchema.create({ blockSpecs: { paragraph: defaultBlockSpecs.paragraph, region } });
  const editor = BlockNoteEditor.create({ schema, initialContent: [
    { id: "header", type: "region", children: [{ id: "name", type: "paragraph", content: [{ type: "text", text: "Candidate 42", styles: { bold: true } }] }] },
    { id: "sidebar", type: "region", children: [{ id: "education", type: "paragraph", content: "Course 2024", children: [{ id: "detail", type: "paragraph", content: "Keep nested text" }] }] },
    { id: "main", type: "region", children: [{ id: "work", type: "paragraph", content: "Keep current wording" }] },
  ] });
  const formatted = editor.document.map(block => ({ id: block.id, children: block.children }));
  const main = formatted.find(region => region.id === "main"); assert.ok(main);
  const flattened = formatted.map(region => ({ id: region.id, children: region.id === "main" ? formatted.flatMap(area => area.children) : [] }));
  const project = (regions: typeof formatted) => editor.transact(tr => projectRegionChildren(tr, regions,
    (id, children) => editor.updateBlock(id, { children })));
  const history = new SessionHistory("region-test", new Map([["layout", "formatted"]]), changes => {
    assert.equal(changes.length, 1); project(changes[0]?.after === "flat" ? flattened : formatted);
  });
  assert.ok(history.commit("structure", [{ key: "layout", before: "formatted", after: "flat" }]));
  assert.deepEqual(editor.document.map(block => ({ id: block.id, children: block.children })), flattened);
  assert.equal(history.length, 1);
  assert.ok(history.undo());
  assert.deepEqual(editor.document.map(block => ({ id: block.id, children: block.children })), formatted);
  assert.ok(history.redo());
  assert.deepEqual(editor.document.map(block => ({ id: block.id, children: block.children })), flattened);
  const before = editor.document;
  assert.throws(() => project([...flattened, { id: "missing-region", children: [] }]), /missing/);
  assert.deepEqual(editor.document, before);
  assert.throws(() => project([{ id: "name", children: [] }]), /not a region/);
  assert.deepEqual(editor.document, before);
  assert.throws(() => editor.transact(tr => projectRegionChildren(tr, formatted, () => { throw new Error("Projection failed"); })), /Projection failed/);
  assert.deepEqual(editor.document, before);
});
