import assert from "node:assert/strict";
import test from "node:test";
import { Schema } from "@tiptap/pm/model";
import { EditorState, TextSelection } from "@tiptap/pm/state";
import { history, undoDepth } from "@tiptap/pm/history";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { presentationPlugin, type PresentationBlocks } from "../src/rich/presentation";

test("template decorations leave authored text marks and history untouched and admit only bundled logos", () => {
  const schema = new Schema({ nodes: {
    doc: { content: "blockContainer+" }, blockContainer: { content: "paragraph", attrs: { id: { default: "" } } },
    paragraph: { content: "inline*" }, text: { group: "inline" },
    factField: { inline: true, group: "inline", content: "text*" },
  }, marks: { bold: {} } });
  const doc = schema.node("doc", null, [schema.node("blockContainer", { id: "focus" }, schema.node("paragraph", null,
    schema.text("Python", [schema.mark("bold")]))), schema.node("blockContainer", { id: "empty" }, schema.node("paragraph", null,
    schema.node("factField")))]);
  let roles: PresentationBlocks = { focus: { role: "focus_entry", logo: "safe" }, empty: { role: "support", logo: "https://untrusted.example/logo.png" } };
  const plugin = presentationPlugin(() => roles, new Map([["safe", "/assets/python.png"]]));
  let state = EditorState.create({ doc, plugins: [history(), plugin], selection: TextSelection.create(doc, 3) });
  const before = doc.toJSON() as unknown;
  const decorations = () => {
    const value = plugin.props.decorations?.call(plugin, state);
    assert.ok(value instanceof DecorationSet); return value.find();
  };
  assert.equal(decorations().length, 2);
  const first = decorations()[0], second = decorations()[1]; assert.ok(first && second);
  assert.deepEqual(first, Decoration.node(first.from, first.to, { "data-cv-role": "focus_entry", "data-cv-logo": "true",
    "data-cv-bound": "false", "data-cv-empty": "false", "data-cv-active": "true",
    "style": '--cv-focus-logo: url("/assets/python.png")' }));
  assert.deepEqual(second, Decoration.node(second.from, second.to, { "data-cv-role": "support", "data-cv-logo": "false",
    "data-cv-bound": "true", "data-cv-empty": "true", "data-cv-active": "false" }));
  roles = { focus: { role: "body" } };
  const tr = state.tr.setMeta("foldcv-presentation", true);
  assert.equal(tr.docChanged, false);
  state = state.apply(tr);
  assert.equal(decorations().length, 1);
  assert.deepEqual(state.doc.toJSON(), before);
  assert.equal(undoDepth(state), 0);
});
