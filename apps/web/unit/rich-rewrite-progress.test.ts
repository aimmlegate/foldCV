import assert from "node:assert/strict";
import test from "node:test";
import fixedFixture from "../../../contracts/examples/background/background_fixed_reply_v1.json" with { type: "json" };
import savedFixture from "../../../contracts/examples/background/background_saved_snapshot_v1.json" with { type: "json" };
import { backgroundReply } from "../src/background/api";
import { rewriteStage, type RewriteActivity } from "../src/rich/rewrite-progress";
import type { RichRewriteRequest } from "../src/contracts/generated/rich_rewrite_request";
import type { RichSelection } from "../src/contracts/generated/rich_selection";
import { validateContract } from "../src/contracts/validate";
import { panelHarness } from "./rich-panel-harness";

function gate() { let release = () => {}; const wait = new Promise<void>(resolve => { release = resolve; }); return { wait, release }; }
const selection = (): RichSelection => ({ kind: "text", blockIds: ["narrative"],
  anchor: { blockId: "narrative", cellId: null, offset: 0 }, head: { blockId: "narrative", cellId: null, offset: 6 },
  textSha256: "0".repeat(64), capture: { sessionId: "queue-session", actionId: "request", actionToken: 0, dependencies: [] } });

for (const cut of ["saving", "running", "undo"] as const) test(`cancelling a rewrite with ${cut} keeps unrelated edits and rejects a late valid reply`, { timeout: 30000 }, async context => {
  const progress: RewriteActivity[] = [], held = gate(), entered = gate(), stopped = gate();
  const h = panelHarness({ rewriteProgress: value => { progress.push(value); if (value.stage === "cancelled") stopped.release(); } });
  const fallback = globalThis.fetch;
  let requests = 0, cancellations = 0, previews = 0;
  if (cut === "saving") {
    const flush = h.queue.flush.bind(h.queue);
    h.queue.flush = async () => { entered.release(); await held.wait; return flush(); };
  }
  globalThis.fetch = async (input, init) => {
    const path = String(input);
    if (path.endsWith("/rewrite")) {
      requests++; entered.release();
      const raw: unknown = JSON.parse(String(init?.body)); assert.ok(validateContract("rich_rewrite_request", raw));
      const request = raw as RichRewriteRequest;
      await held.wait;
      const response = structuredClone(h.queue.baseline);
      const block = response.workspace.project?.document.regions[2].blocks.find(block => block.id === "narrative");
      assert.ok(block && block.type === "paragraph");
      block.content = [{ type: "text", text: "Late replacement", styles: { bold: false, italic: false, underline: false, strike: false, code: false, textColor: "default", backgroundColor: "default" } }];
      response.workspace.syncRecords.push({ id: "late-rewrite", kind: "rewrite", status: "pending", ready: true,
        actionId: request.selection.capture.actionId, blockIds: [block.id], fieldKeys: [], factIds: [], dependencies: [], errorCode: null,
        proposedSteps: [{ kind: "put_block", block, parentId: "main", afterId: null, beforeRevision: block.revision, keepChildren: false }], selection: request.selection, instruction: request.instruction });
      return Response.json(response);
    }
    if (path.endsWith("/cancel-action")) { cancellations++; return Response.json(h.queue.baseline); }
    if (path.endsWith("/preview")) previews++;
    return fallback(input, init);
  };
  context.after(() => { held.release(); h.close(); });
  const original = h.document();
  const pending = h.sync.rewrite(selection(), "Clarify");
  await entered.wait;
  const action = progress[0]; assert.ok(action); assert.equal(progress.at(-1)?.stage, cut === "undo" ? "running" : cut);
  if (cut === "undo") { assert.ok(h.history.undo()); h.sync.invalidate(); await stopped.wait; }
  else {
    h.history.commit("typing", [{ key: "unrelated", before: null, after: "Keep this edit" }]);
    await h.sync.cancelRewrite(action.actionId);
  }
  assert.equal(progress.at(-1)?.stage, "cancelled");
  held.release(); await pending;
  assert.equal(cancellations, 1); assert.equal(requests, cut === "saving" ? 0 : 1); assert.equal(previews, 0);
  assert.deepEqual(h.document(), original); assert.equal(h.history.read("unrelated"), cut === "undo" ? null : "Keep this edit");
  assert.equal(h.history.length, cut === "undo" ? 0 : 1); assert.equal(progress.at(-1)?.stage, "cancelled");
});

test("a failed cancellation stays explicit instead of reporting that the request stopped", async context => {
  const progress: RewriteActivity[] = [], entered = gate(), held = gate();
  const h = panelHarness({ rewriteProgress: value => progress.push(value) }), fallback = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    if (String(input).endsWith("/rewrite")) { entered.release(); await held.wait; throw new Error("Closed connection"); }
    if (String(input).endsWith("/cancel-action")) throw new Error("Offline");
    return fallback(input, init);
  };
  context.after(() => { held.release(); h.close(); });
  const pending = h.sync.rewrite(selection(), "Clarify"); await entered.wait;
  const action = progress[0]; assert.ok(action);
  await h.sync.cancelRewrite(action.actionId);
  assert.equal(progress.at(-1)?.stage, "failed"); assert.match(progress.at(-1)?.detail ?? "", /Не удалось подтвердить отмену/u);
  held.release(); await pending;
  assert.equal(progress.at(-1)?.stage, "failed");
});

test("rewrite progress distinguishes model completion, pending publication, review and durable save", async () => {
  const { job } = await backgroundReply("background_fixed_reply_v1", fixedFixture);
  assert.equal(rewriteStage({ ...job, execution: "queued", publication: "none", receipt: null }), "queued");
  assert.equal(rewriteStage({ ...job, execution: "completed", publication: "ready", receipt: null }), "applying");
  assert.equal(rewriteStage({ ...job, execution: "completed", publication: "needs_review", receipt: null }), "review");
  assert.equal(rewriteStage({ ...job, execution: "cancelling", publication: "none", receipt: null }), "cancelling");
  const saved = await backgroundReply("background_snapshot_v1", savedFixture);
  assert.equal(rewriteStage({ ...saved, execution: "cancelled" }), "saved");
});

