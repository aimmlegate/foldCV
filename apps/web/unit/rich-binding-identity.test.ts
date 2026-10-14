import assert from "node:assert/strict";
import test from "node:test";
import { Schema } from "@tiptap/pm/model";
import { EditorState } from "@tiptap/pm/state";
import { bindingIdentityPlugin } from "../src/rich/binding-identity";

test("rich inline paste creates a fresh binding and keeps the mapped original fact identity", () => {
  const schema = new Schema({ nodes: {
    doc: { content: "paragraph+" }, paragraph: { content: "inline*" }, text: { group: "inline" },
    factField: { inline: true, group: "inline", content: "text*", attrs: { bindingId: { default: "" }, recordId: { default: "" } } },
  }, marks: { italic: {} } });
  const field = schema.nodes["factField"], paragraph = schema.nodes["paragraph"];
  assert.ok(field && paragraph);
  const original = field.create({ bindingId: "original", recordId: "candidate" }, schema.text("Alex"));
  let counter = 0;
  const state = EditorState.create({ schema, doc: schema.nodes["doc"]?.create(null, paragraph.create(null, original)),
    plugins: [bindingIdentityPlugin(() => `fresh-${++counter}`)] });
  const copied = state.applyTransaction(state.tr.insert(1, original)).state;
  const bindings: { id: unknown; record: unknown }[] = [];
  copied.doc.descendants(node => { if (node.type.name === "factField") bindings.push({ id: node.attrs["bindingId"], record: node.attrs["recordId"] }); });
  assert.deepEqual(bindings, [{ id: "fresh-1", record: "candidate" }, { id: "original", record: "candidate" }]);
  const italic = schema.marks["italic"]; assert.ok(italic);
  const styled = copied.applyTransaction(copied.tr.addMark(3, 4, italic.create())).state;
  const ids: unknown[] = []; styled.doc.descendants(node => { if (node.type.name === "factField") ids.push(node.attrs["bindingId"]); });
  assert.deepEqual(ids, ["fresh-1", "original"]);
});
