import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import type { AgentFinding } from "../src/contracts/generated/agent_finding";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { documentCells } from "../src/rich/document-cells";
import { factCells } from "../src/rich/fact-cells";
import type { RichBlock } from "../src/rich/save-queue";
import { anchorCurrent, drawerSize, sourceUrl, submitKey } from "../src/assistant/presentation";
import { Messages } from "../src/assistant/Messages";

test("assistant findings reject changed revisions and unsaved target cells without matching text", () => {
  const workspace: unknown = structuredClone(fixture); assert.ok(validateRichWorkspaceShape(workspace)); assert.ok(workspace.project);
  const response: RichProjectResponse = { workspace, durability: "durable", savedProjectRevision: 1, savedDocumentRevision: 1, saveError: null, generation: null };
  const flatten = (items: RichBlock[]): RichBlock[] => items.flatMap(item => [item, ...flatten(item.children)]);
  const block = workspace.project.document.regions.flatMap(region => flatten(region.blocks)).find(item => item.id === "narrative"); assert.ok(block);
  const anchor: AgentFinding["anchors"][number] = { blockId: block.id, cellId: null, recordId: null, fieldKey: null, start: 0, end: 6,
    text: "Python", dependencies: [{ kind: "block", id: block.id, revision: block.revision, fingerprint: "a".repeat(64) }] };
  const cells = new Map([...documentCells(workspace.project.document, new Map()), ...factCells(workspace.project.facts)]);
  assert.ok(anchorCurrent(anchor, response, cells));
  cells.set("block:unrelated", "Manual text"); assert.ok(anchorCurrent(anchor, response, cells));
  cells.set("block:narrative", "Changed Python"); assert.equal(anchorCurrent(anchor, response, cells), false);
  assert.equal(anchorCurrent({ ...anchor, blockId: "missing" }, response, cells), false);
  block.revision++; assert.equal(anchorCurrent(anchor, response, cells), false);
});

test("assistant message markup stays plain text and stored source URLs reject active schemes", () => {
  const html = renderToStaticMarkup(createElement(Messages, { items: [{ id: "m1", role: "assistant", runId: "r1", timestamp: "2026-10-15T12:00:00Z",
    text: '<img src="https://unretrieved.example/pixel"> [link](https://unretrieved.example) https://unretrieved.example', sources: [], findings: [], truncated: false, error: null }],
    partial: "", truncated: false, resource: () => {} }));
  assert.equal(/<img|<a\s/.test(html), false); assert.ok(html.includes("&lt;img"));
  for (const value of ["javascript:alert(1)", "data:text/html,test", "https://user:secret@example.com", "invalid"]) assert.equal(sourceUrl(value), null);
  assert.equal(sourceUrl("https://example.com/vacancy"), "https://example.com/vacancy");
});

test("assistant drawer persistence contains only bounded dimensions and collapse state", () => {
  assert.deepEqual(drawerSize(null), { collapsed: true, height: 320 });
  assert.deepEqual(drawerSize({ height: 10000, collapsed: false, token: "do-not-store", messages: ["private"] }), { height: 520, collapsed: false });
  assert.deepEqual(drawerSize({ height: NaN, collapsed: "bad" }), { height: 320, collapsed: true });
});

test("assistant Enter sends only outside composition and Shift retains a newline", () => {
  assert.ok(submitKey("Enter", false, false, false, 13));
  assert.equal(submitKey("Enter", true, false, false, 13), false);
  assert.equal(submitKey("Enter", false, true, false, 13), false);
  assert.equal(submitKey("Enter", false, false, true, 13), false);
  assert.equal(submitKey("Enter", false, false, false, 229), false);
  assert.equal(submitKey("a", false, false, false, 65), false);
});
