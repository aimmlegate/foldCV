import assert from "node:assert/strict";
import test from "node:test";
import { Fragment, Schema, Slice } from "@tiptap/pm/model";
import { AllSelection, EditorState, TextSelection } from "@tiptap/pm/state";
import { deleteAcrossRegions, pastedRegionsPlugin, flattenPastedRegions } from "../src/rich/regions";
import { readBlockSources, structureIdentityPlugin } from "../src/rich/structure-identity";

const schema = new Schema({ nodes: { doc: { content: "blockGroup" }, blockGroup: { content: "blockContainer+" },
  blockContainer: { content: "(region|paragraph|section) blockGroup?", attrs: { id: { default: "" }, foldcvSources: { default: null } } },
  region: { atom: true }, paragraph: { content: "text*" }, section: { content: "text*", attrs: { recordId: { default: "" } } }, text: {} } });
function block(id: string, text: string) { return schema.node("blockContainer", { id }, schema.node("paragraph", null, text ? schema.text(text) : undefined)); }
function fixture() {
  const roots = ["header", "sidebar", "main"].map((role, index) => schema.node("blockContainer", { id: role },
    [schema.node("region"), schema.node("blockGroup", null, block(`block-${index}`, role))]));
  return EditorState.create({ schema, doc: schema.node("doc", null, schema.node("blockGroup", null, roots)), plugins: [pastedRegionsPlugin()] });
}

test("deleting cross-region text keeps all three fixed containers and the unselected ends", () => {
  let state = fixture();
  const positions: number[] = []; state.doc.descendants((node, pos) => { if (node.isText) positions.push(pos); });
  const start = positions[0], end = positions[2]; assert.ok(start !== undefined && end !== undefined);
  state = state.apply(state.tr.setSelection(TextSelection.create(state.doc, start + 2, end + 2)));
  const transaction = deleteAcrossRegions(state); assert.ok(transaction);
  state = state.applyTransaction(transaction).state;
  assert.equal(state.doc.firstChild?.childCount, 3);
  assert.deepEqual([0, 1, 2].map(index => { const id: unknown = state.doc.firstChild?.child(index).attrs["id"]; return id; }), ["header", "sidebar", "main"]);
  assert.equal(state.doc.textContent, "hein");
  const full = state.tr.setSelection(new AllSelection(state.doc));
  state = state.apply(full); const cleared = deleteAcrossRegions(state); assert.ok(cleared);
  state = state.applyTransaction(cleared).state;
  assert.equal(state.doc.textContent, ""); assert.equal(state.doc.firstChild?.childCount, 3);
});

test("a pasted region unwraps its content and a copied owner cites the mapped original", () => {
  let state = fixture();
  const nested = schema.node("blockContainer", { id: "copied-main" }, [schema.node("region"), schema.node("blockGroup", null, block("copy", "Paste"))]);
  const pos = state.doc.content.size - 3;
  state = state.applyTransaction(state.tr.insert(pos, nested)).state;
  let regionCount = 0; state.doc.descendants(node => { if (node.type.name === "region") regionCount++; });
  assert.equal(regionCount, 3); assert.ok(state.doc.textContent.includes("Paste"));
  const original = schema.node("blockContainer", { id: "original", foldcvSources: '["original"]' }, schema.node("section", { recordId: "job" }, schema.text("Job")));
  const copy = schema.node("blockContainer", { id: "copy", foldcvSources: '["original"]' }, schema.node("section", { recordId: "job" }, schema.text("Job")));
  state = EditorState.create({ schema, doc: schema.node("doc", null, schema.node("blockGroup", null, original)), plugins: [structureIdentityPlugin()] });
  state = state.applyTransaction(state.tr.insert(1, copy)).state;
  const owners: string[] = []; state.doc.descendants(node => { if (node.type.name === "section") owners.push(String(node.attrs["recordId"])); });
  assert.deepEqual(owners, ["", "job"]); assert.deepEqual(readBlockSources(state.doc).get("copy"), ["original"]);
});

test("whole-document paste unwraps its layout before insertion and keeps every authored block", () => {
  const state = fixture(), group = state.doc.firstChild; assert.ok(group);
  const flattened = flattenPastedRegions(new Slice(Fragment.from(group), 0, 0)); assert.ok(flattened);
  assert.equal(flattened.openStart, 0); assert.equal(flattened.content.childCount, 3);
  assert.equal(flattened.content.textBetween(0, flattened.content.size), "headersidebarmain");
  assert.deepEqual(flattened.content.content.map(node => { const id: unknown = node.attrs["id"]; return id; }), ["block-0", "block-1", "block-2"]);
  assert.equal(flattenPastedRegions(new Slice(Fragment.from(block("plain", "Plain paste")), 0, 0)), null);
});
