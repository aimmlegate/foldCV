import assert from "node:assert/strict";
import test from "node:test";
import { Schema } from "@tiptap/pm/model";
import { AllSelection, EditorState, TextSelection } from "@tiptap/pm/state";
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
    "data-cv-experience": "false",
    "data-cv-bound": "false", "data-cv-empty": "false", "data-cv-marker": "false", "data-cv-active": "true",
    "style": '--cv-focus-logo: url("/assets/python.png")' }));
  assert.deepEqual(second, Decoration.node(second.from, second.to, { "data-cv-role": "support", "data-cv-logo": "false",
    "data-cv-experience": "false",
    "data-cv-bound": "true", "data-cv-empty": "true", "data-cv-marker": "false", "data-cv-active": "false" }));
  roles = { focus: { role: "body" } };
  const tr = state.tr.setMeta("foldcv-presentation", true);
  assert.equal(tr.docChanged, false);
  state = state.apply(tr);
  assert.equal(decorations().length, 1);
  assert.deepEqual(state.doc.toJSON(), before);
  assert.equal(undoDepth(state), 0);
});

test("an authored list marker stays in the text and suppresses a second marker", () => {
  const schema = new Schema({ nodes: {
    doc: { content: "blockContainer" }, blockContainer: { content: "paragraph", attrs: { id: { default: "list" } } },
    paragraph: { content: "text*" }, text: {},
  } });
  const doc = schema.node("doc", null, schema.node("blockContainer", null,
    schema.node("paragraph", null, schema.text("- Original task."))));
  const plugin = presentationPlugin(() => ({ list: { role: "body" } }), new Map());
  const state = EditorState.create({ doc, selection: new AllSelection(doc), plugins: [history(), plugin] });
  const set = plugin.props.decorations?.call(plugin, state);
  assert.ok(set instanceof DecorationSet);
  const decoration = set.find()[0]; assert.ok(decoration);
  assert.deepEqual(decoration, Decoration.node(decoration.from, decoration.to, { "data-cv-role": "body", "data-cv-logo": "false",
    "data-cv-experience": "false",
    "data-cv-bound": "false", "data-cv-empty": "false", "data-cv-marker": "true", "data-cv-active": "false" }));
  assert.equal(state.doc.textContent, "- Original task.");
  assert.equal(undoDepth(state), 0);
});

test("duration labels remain derived decorations and leave authored text and undo untouched", () => {
  const schema = new Schema({ nodes: {
    doc: { content: "blockContainer" }, blockContainer: { content: "paragraph", attrs: { id: { default: "tech" } } },
    paragraph: { content: "text*" }, text: {},
  } });
  const doc = schema.node("doc", null, schema.node("blockContainer", null, schema.node("paragraph", null, schema.text("Python"))));
  const roles: PresentationBlocks = { tech: { role: "focus_entry", experience: "3 года", experienceNote: "По датам мест работы" } };
  const plugin = presentationPlugin(() => roles, new Map());
  const state = EditorState.create({ doc, selection: new AllSelection(doc), plugins: [history(), plugin] });
  const set = plugin.props.decorations?.call(plugin, state);
  assert.ok(set instanceof DecorationSet);
  assert.equal(set.find().length, 2);
  assert.equal(set.find().filter(d => {
    const spec: unknown = d.spec;
    return typeof spec === "object" && spec !== null && "key" in spec && spec.key === "experience:tech:3 года:По датам мест работы";
  }).length, 1);
  assert.equal(state.doc.textContent, "Python");
  assert.equal(undoDepth(state), 0);
});
