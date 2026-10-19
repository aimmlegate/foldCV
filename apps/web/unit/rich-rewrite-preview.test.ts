import assert from "node:assert/strict";
import test from "node:test";
import type { RichRewriteRequest } from "../src/contracts/generated/rich_rewrite_request";
import type { RichSelection } from "../src/contracts/generated/rich_selection";
import Ajv2020 from "ajv/dist/2020.js";
import schema from "../../../contracts/json-schema/rich_rewrite_request.schema.json" with { type: "json" };
import { singleRewriteRange } from "../src/rich/selection";
import { panelHarness } from "./rich-panel-harness";
import type { RichBlock } from "../src/rich/save-queue";
import { SessionHistory } from "../src/rich/history";
import { validateContract } from "../src/contracts/validate";

const validateRequest = new Ajv2020({ strict: false }).compile<RichRewriteRequest>(schema);

test("reopening a writer session cannot reuse a previous rewrite action ID", () => {
  const first = new SessionHistory("writer", new Map(), undefined, undefined, "opening-one");
  const second = new SessionHistory("writer", new Map(), undefined, undefined, "opening-two");
  const changes = [{ key: "request:preview", before: null, after: "pending" }];
  const a = first.commit("rewrite", changes), b = second.commit("rewrite", changes);
  assert.ok(a && b); assert.notEqual(a, b); assert.equal(first.capture(a, [])?.session, "writer");
});

const selection = (): RichSelection => ({ kind: "text", blockIds: ["narrative"],
  anchor: { blockId: "narrative", cellId: null, offset: 0 }, head: { blockId: "narrative", cellId: null, offset: 6 },
  textSha256: "0".repeat(64), capture: { sessionId: "queue-session", actionId: "request", actionToken: 0, dependencies: [] } });

test("rewrite scope accepts one text block or table cell and rejects cross-block, cross-column and cell ranges", () => {
  const one = selection();
  assert.equal(singleRewriteRange(one), true);
  assert.equal(singleRewriteRange({ ...one, blockIds: ["narrative", "sidebar"], head: { ...one.head, blockId: "sidebar" } }), false);
  assert.equal(singleRewriteRange({ ...one, head: { ...one.head, offset: 0 } }), false);
  const cell = { ...one, kind: "table_cells" as const, anchor: { ...one.anchor, cellId: "cell-1" }, head: { ...one.head, cellId: "cell-1" } };
  assert.equal(singleRewriteRange(cell), true);
  assert.equal(singleRewriteRange({ ...cell, head: { ...cell.head, cellId: "cell-2" } }), false);
});

test("queued preview contracts enforce the same single-target boundary as the server", () => {
  const request = { schemaVersion: 1, lineage: "lineage", requestEpoch: 1, clientRequestId: "preview-request",
    command: { kind: "rewrite", request: { selection: selection(), instruction: "Clarify", previewOnly: true } } };
  assert.equal(validateContract("background_fixed_request_v1", request), true);
  request.command.request.selection.head.blockId = "other-block";
  request.command.request.selection.blockIds.push("other-block");
  assert.equal(validateContract("background_fixed_request_v1", request), false);
});

for (const outcome of ["apply", "delete", "cancel"] as const) test(`preview keeps document, facts and history unchanged before ${outcome}`, async context => {
  const h = panelHarness(), fallback = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async (input, init) => {
    if (String(input).endsWith("/rewrite")) {
      calls++;
      const raw: unknown = JSON.parse(String(init?.body));
      assert.ok(validateRequest(raw));
      const request = raw;
      assert.equal(request.previewOnly, true);
      const flatten = (blocks: RichBlock[]): RichBlock[] => blocks.flatMap(block => [block, ...flatten(block.children)]);
      const response = structuredClone(h.queue.baseline), block = response.workspace.project?.document.regions.flatMap(region => flatten(region.blocks)).find(block => block.id === "narrative");
      assert.ok(block && block.type === "paragraph");
      block.content = [{ type: "text", text: "Clearer: Styled workExact URL", styles: { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" } }];
      response.workspace.syncRecords.push({ id: "rewrite-result", actionId: request.selection.capture.actionId, kind: "rewrite", status: "pending", ready: true,
        blockIds: [block.id], fieldKeys: [], factIds: [], dependencies: [], errorCode: null, selection: request.selection, instruction: request.instruction,
        rewriteSource: "Styled", rewriteResult: "Clearer: Styled", proposedSteps: [{ kind: "put_block", parentId: "job-section", afterId: null, beforeRevision: block.revision, block, keepChildren: false }] });
      return Response.json(response);
    }
    return fallback(input, init);
  };
  context.after(() => h.close());
  const document = h.document(), facts = h.facts();
  await h.sync.rewrite(selection(), "Clarify", true);
  assert.deepEqual(h.document(), document); assert.deepEqual(h.facts(), facts); assert.equal(h.history.length, 0);
  const preview = h.sync.previewRewrite("queue-session:1");
  assert.ok(preview, "Preview retains its originating action");
  const action = preview.actionId;
  if (outcome === "delete") {
    h.history.commit("structure", [{ key: "block:narrative", before: h.history.read("block:narrative"), after: null }]);
    await assert.rejects(h.sync.applyRewrite(action), /STALE_SELECTION/u);
    assert.equal(h.history.read("block:narrative"), null);
  } else if (outcome === "cancel") {
    await h.sync.cancelRewrite(action);
    await assert.rejects(h.sync.applyRewrite(action), /STALE_SELECTION/u);
    assert.deepEqual(h.document(), document);
  } else {
    h.history.commit("typing", [{ key: "unrelated", before: null, after: "Keep this edit" }]);
    await h.sync.applyRewrite(action);
    assert.notDeepEqual(h.document(), document);
    assert.equal(h.history.read("unrelated"), "Keep this edit");
    assert.ok(h.history.undo()); assert.deepEqual(h.document(), document);
    assert.equal(h.history.read("unrelated"), "Keep this edit");
  }
  assert.equal(calls, 1);
});
