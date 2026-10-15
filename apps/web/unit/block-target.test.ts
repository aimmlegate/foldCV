import assert from "node:assert/strict";
import test from "node:test";
import { commandBlock } from "../src/rich/block-target";

test("block actions retain the menu target after the cursor moves elsewhere", () => {
  const blocks = new Map([
    ["menu-target", { id: "menu-target", type: "paragraph", text: "Selected block" }],
    ["cursor", { id: "cursor", type: "paragraph", text: "Other block" }],
  ]);
  let cursor = "menu-target";
  const captured = cursor;
  cursor = "cursor";
  const selected = commandBlock(captured, id => blocks.get(id));
  selected.text = "Changed target";
  assert.equal(blocks.get(cursor)?.text, "Other block");
  assert.equal(blocks.get(captured)?.text, "Changed target");
  blocks.delete(captured);
  assert.throws(() => commandBlock(captured, id => blocks.get(id)), /Блок недоступен/);
  assert.equal(blocks.get(cursor)?.text, "Other block");
});

test("fixed layout regions cannot become block-action targets", () => {
  assert.throws(() => commandBlock("header", () => ({ id: "header", type: "region" })), /Блок недоступен/);
});
