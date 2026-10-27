import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { BlockNoteEditor } from "@blocknote/core";
import type { Node } from "@tiptap/pm/model";
import type { RichDocumentV2 } from "../src/contracts/generated/rich_document_v2";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { contentText, responseBlocks } from "../src/rich/v7-response";
import { templateSchema } from "../src/rich/template-schema";
import { projectTemplateDocument } from "../src/rich/v7-projection";

function record(value: unknown): Record<string, unknown> {
  assert.ok(typeof value === "object" && value !== null && !Array.isArray(value));
  return Object.fromEntries(Object.entries(value));
}
const fixture = record(JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/templates/address-maps.json", import.meta.url), "utf8")));
assert.ok(Array.isArray(fixture["cases"]));
const responses = fixture["cases"].flatMap((row: unknown) => {
  const value = record(row);
  return [value["baseWire"], value["resultWire"]].filter((wire): wire is string => typeof wire === "string")
    .map(wire => JSON.parse(wire) as TemplateProjectResponseV1);
});
function documentOf(response: TemplateProjectResponseV1): RichDocumentV2 {
  const value = response.workspace.project?.document;
  assert.ok(value && Array.isArray(value.regions)); return value;
}

function editorDoc(document: RichDocumentV2): Node {
  const editor = BlockNoteEditor.create({ schema: templateSchema, initialContent: projectTemplateDocument(document) });
  const doc = editor._tiptapEditor.state.doc;
  editor._tiptapEditor.destroy();
  return doc;
}

/** Editor-side text per container, keyed like the address verifier's blocks. */
function editorTexts(doc: Node): Map<string, string> {
  const result = new Map<string, string>();
  doc.descendants(node => {
    const id: unknown = node.attrs["id"];
    if (node.type.name !== "blockContainer" || typeof id !== "string") return;
    const content = node.firstChild;
    if (content && content.type.name !== "region" && content.type.name !== "table" && content.type.name !== "image") result.set(id, content.textContent);
  });
  return result;
}

test("every fixture document projects with identical container text and block identities", () => {
  assert.ok(responses.length >= 20);
  let containers = 0;
  for (const response of responses) {
    const texts = editorTexts(editorDoc(documentOf(response)));
    for (const [id, block] of responseBlocks(response)) for (const group of block.groups) {
      if (group.kind !== "content") continue;
      assert.equal(texts.get(id), contentText(group.content), id);
      containers++;
    }
  }
  assert.ok(containers >= 40);
});

test("field, scope and empty-anchor identities ride on editor nodes for input sides", () => {
  const base = responses.find(response => contentText(responseBlocks(response).get("block-paper-a")?.groups[0]?.content ?? [])
    .startsWith("By Shared title"));
  assert.ok(base);
  const value = documentOf(base);
  const fields: Record<string, unknown>[] = [];
  editorDoc(value).descendants(node => { if (node.type.name === "templateField") fields.push({ ...node.attrs, text: node.textContent }); });
  assert.ok(fields.some(field => field["bindingId"] === "fragment-paper-a" && field["occurrenceId"] === "occurrence-paper-a"
    && field["cellId"] === "a-title" && field["text"] === "Shared title"));
  // An emptied field keeps an explicit zero-length node so typing can still name it.
  const emptied = structuredClone(value);
  const block = emptied.regions[2]?.blocks[0];
  assert.ok(block && block.type === "paragraph");
  const field = block.content.find(span => span.type === "fact_field");
  assert.ok(field && field.type === "fact_field"); field.text = "";
  const anchors: string[] = [];
  editorDoc(emptied).descendants(node => { if (node.type.name === "templateField" && node.textContent === "") anchors.push(String(node.attrs["bindingId"])); });
  assert.deepEqual(anchors, [field.bindingId]);
});
