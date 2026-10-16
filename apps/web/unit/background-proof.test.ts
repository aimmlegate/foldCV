import assert from "node:assert/strict";
import test from "node:test";
import { backgroundReply } from "../src/background/api";
import { validateBackgroundWire } from "../src/contracts/background-validate";
import { sha256 } from "../src/background/wire";
import { offer, saved, published, newerOffer, harness } from "./support/background-writer";

for (let index = 1; index <= 7; index++) {
  test(`NB-W12:v${String(index).padStart(2, "0")} invalid saved proof cannot authorize adoption or a saved notice`, async () => {
    const altered = structuredClone(offer), receipt = altered.job.receipt; assert.ok(receipt);
    if (index === 1) receipt.projectId = "different-project";
    else if (index === 2) altered.job.id = "different-job";
    else if (index === 3) altered.batchId = "different-batch";
    else if (index === 4) receipt.workspaceSha256 = "f".repeat(64);
    else if (index === 5) Object.assign(receipt, { durable: false });
    else if (index === 6) {
      altered.saved.workspace.mutationReplay = []; altered.savedWire = JSON.stringify(altered.saved.workspace);
      receipt.workspaceSha256 = await sha256(altered.savedWire);
    } else altered.saved.savedProjectRevision = altered.saved.workspace.projectRevision + 1;
    assert.equal(await validateBackgroundWire("background_writer_history_offer_v1", altered), false);
    const h = harness({ headless: true });
    h.offerReply(() => backgroundReply("background_writer_history_offer_v1", altered));
    try {
      await assert.rejects(h.writer.adoptHeadless(saved), /INVALID_RESULT/u);
      assert.equal(h.counts.notices, 0); assert.equal(h.history.length, 0); assert.equal(h.counts.ownership, 0);
      assert.deepEqual(h.mounted, h.cells(published.response));
    } finally { h.close(); }
  });
}

test("saved snapshot bytes reject hash-preserving structural substitution", async () => {
  const view = structuredClone(published); view.response.workspace.title = "Changed outside the proof bytes";
  assert.equal(await validateBackgroundWire("background_writer_view_v1", view), false);
});

test("NB-W12:v08 a true older receipt adopts only its inverse and preserves the newer canonical snapshot", async () => {
  assert.ok(saved.receipt);
  assert.ok(newerOffer.view.response.workspace.projectRevision > saved.receipt.projectRevision);
  assert.ok(await validateBackgroundWire("background_writer_history_offer_v1", newerOffer));
  const h = harness({ headless: true, initialView: newerOffer.view }), current = new Map(h.mounted);
  h.offerReply(() => Promise.resolve(newerOffer));
  try {
    await h.writer.adoptHeadless(saved);
    assert.deepEqual(h.mounted, current);
    assert.equal(h.queue.baseline.workspace.projectRevision, newerOffer.view.response.workspace.projectRevision);
    assert.equal(h.history.length, 1); assert.equal(h.counts.commits, 0); assert.equal(h.counts.saves, 0);
  } finally { h.close(); }
});
