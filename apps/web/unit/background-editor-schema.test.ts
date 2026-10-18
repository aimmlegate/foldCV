import assert from "node:assert/strict";
import test from "node:test";
import { getSchema, Node } from "@tiptap/core";
import { BlockNoteSchema } from "@blocknote/core";
import { allowRichCodeStyles, allowRichColors } from "../src/rich/styles";

test("rich history adoption accepts code, emphasis and colors in the actual engine schema", () => {
  const blocks = BlockNoteSchema.create(); allowRichCodeStyles(blocks);
  const schema = getSchema([Node.create({ name: "doc", topNode: true, content: "text*" }),
    Node.create({ name: "text", group: "inline" }), ...Object.values(blocks.styleSpecs).map(spec => spec.implementation.mark)]);
  const marks = ["bold", "italic", "underline", "strike", "code", "textColor", "backgroundColor"].map(name => {
    const mark = schema.marks[name]; assert.ok(mark); return mark.create(name.endsWith("Color") ? { stringValue: "#123456" } : {});
  });
  const text = schema.text("Synthetic styled background result", marks), document = schema.node("doc", null, [text]);
  document.check(); assert.equal(document.firstChild?.marks.length, 7);
  const code = schema.marks["code"]; assert.ok(code); assert.equal(code.excludes(schema.marks["bold"] ?? code), false);
  const untouched = BlockNoteSchema.create().styleSpecs["code"]; assert.ok(untouched);
  assert.notEqual(untouched.implementation.mark, blocks.styleSpecs["code"]?.implementation.mark);
});

test("rich colors serialize actual hex marks instead of depending on named palette CSS", () => {
  const blocks = BlockNoteSchema.create(); allowRichColors(blocks);
  const schema = getSchema([Node.create({ name: "doc", topNode: true, content: "text*" }),
    Node.create({ name: "text", group: "inline" }), ...Object.values(blocks.styleSpecs).map(spec => spec.implementation.mark)]);
  for (const [name, property, color] of [["backgroundColor", "background-color", "#EFEFEF"], ["textColor", "color", "#123456"]] as const) {
    const type = schema.marks[name]; assert.ok(type?.spec.toDOM);
    const serialized = type.spec.toDOM(type.create({ stringValue: color }), false);
    assert.deepEqual(serialized, ["span", { "data-style-type": name, "data-value": color, style: `${property}: ${color.toLowerCase()}` }, 0]);
    assert.throws(() => type.spec.toDOM?.(type.create({ stringValue: "url(https://invalid.test)" }), false), /RICH_COLOR_UNSUPPORTED/);
  }
});
