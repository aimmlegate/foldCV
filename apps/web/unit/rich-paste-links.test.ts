import assert from "node:assert/strict";
import test from "node:test";
import { Fragment, Schema, Slice } from "@tiptap/pm/model";
import { EditorState, TextSelection } from "@tiptap/pm/state";
import { authoredPasteTransaction } from "../src/rich/paste-links";

test("rich paste keeps an explicit URL when the display text looks like an email", () => {
  const schema = new Schema({ nodes: { doc: { content: "paragraph+" }, paragraph: { content: "text*" }, text: {} },
    marks: { link: { attrs: { href: {} } }, italic: {} } });
  const paragraph = schema.nodes["paragraph"], doc = schema.nodes["doc"], link = schema.marks["link"], italic = schema.marks["italic"];
  assert.ok(paragraph && doc && link && italic);
  const original = doc.create(null, paragraph.create(null, schema.text("Before after")));
  const state = EditorState.create({ schema, doc: original, selection: TextSelection.create(original, 7) });
  const url = "https://example.com/exact/target?value=1";
  const slice = new Slice(Fragment.from(schema.text("email@example.com", [link.create({ href: url }), italic.create()])), 0, 0);
  const tr = authoredPasteTransaction(state, slice); assert.ok(tr);
  const result = state.apply(tr);
  assert.equal(result.doc.textContent, "Beforeemail@example.com after");
  const pasted = result.doc.firstChild?.child(1);
  assert.equal(pasted?.marks.find(mark => mark.type.name === "link")?.attrs["href"], url);
  assert.ok(pasted?.marks.some(mark => mark.type.name === "italic"));
  assert.equal(authoredPasteTransaction(state, new Slice(Fragment.from(schema.text("plain")), 0, 0)), null);
});
