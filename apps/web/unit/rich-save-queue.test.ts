import assert from "node:assert/strict";
import test from "node:test";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import type { RichDocumentV1 } from "../src/contracts/generated/rich_document_v1";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import type { RichMutation } from "../src/contracts/generated/rich_mutation";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { documentSteps, RichSaveQueue } from "../src/rich/save-queue";

function response(): RichProjectResponse {
  const workspace: unknown = structuredClone(fixture);
  assert.ok(validateRichWorkspaceShape(workspace));
  return { workspace, durability: "durable", savedProjectRevision: workspace.projectRevision,
    savedDocumentRevision: workspace.documentRevision, saveError: null, generation: null };
}
function changed(response: RichProjectResponse, text: string): RichDocumentV1 {
  const document = structuredClone(response.workspace.project?.document);
  assert.ok(document);
  const block = document.regions[0].blocks[0];
  assert.ok(block?.type === "paragraph" || block?.type === "heading");
  block.content = [{ type: "text", text, styles: {} }];
  return document;
}
function apply(response: RichProjectResponse, request: RichMutation): RichProjectResponse {
  const next = structuredClone(response);
  const document = next.workspace.project?.document;
  assert.ok(document);
  for (const step of request.steps) {
    assert.equal(step.kind, "put_block");
    if (step.kind !== "put_block") throw new Error("Unexpected patch");
    const region = document.regions.find(region => region.id === step.parentId);
    assert.ok(region);
    const index = region.blocks.findIndex(block => block.id === step.block.id);
    assert.ok(index >= 0);
    const block = step.block;
    assert.ok(block.type === "heading" || block.type === "paragraph");
    // Python's declared wire order differs from the editor's object insertion order.
    const common = { id: block.id, revision: (step.beforeRevision ?? 0) + 1, provenance: block.provenance, children: block.children };
    region.blocks[index] = block.type === "heading" ? { ...common, type: "heading", props: block.props, content: block.content }
      : { ...common, type: "paragraph", props: block.props, content: block.content };
  }
  next.workspace.documentRevision++; next.workspace.projectRevision++;
  document.revision = next.workspace.documentRevision;
  if (next.workspace.project) next.workspace.project.revision = next.workspace.projectRevision;
  return next;
}

test("delayed autosave acknowledgment preserves newer typing and sends it against the new baseline", async () => {
  const initial = response();
  const sent: RichMutation[] = [];
  let release: (() => void) | undefined;
  const delay = new Promise<void>(resolve => { release = resolve; });
  let baseline = initial;
  const acknowledgments: RichProjectResponse[] = [];
  const queue = new RichSaveQueue(initial, "session", async request => {
    sent.push(request);
    if (sent.length === 1) await delay;
    baseline = apply(baseline, request); return baseline;
  }, value => acknowledgments.push(value));
  queue.update(changed(initial, "First edit"), "typing-1");
  const pending = queue.flush();
  queue.update(changed(initial, "Newer edit"), "typing-2");
  assert.equal(sent.length, 1);
  release?.(); await pending;
  assert.equal(sent.length, 2);
  const first = sent[0]?.steps[0], second = sent[1]?.steps[0];
  assert.ok(first?.kind === "put_block" && second?.kind === "put_block");
  assert.equal(second.beforeRevision, (first.beforeRevision ?? 0) + 1);
  assert.equal(acknowledgments.length, 2);
  assert.deepEqual(documentSteps(queue.baseline.workspace.project?.document ?? changed(initial, ""), changed(initial, "Newer edit")), []);
});

test("closing the editor ignores late acknowledgments and never sends its pending next edit", async () => {
  const initial = response();
  let release: (() => void) | undefined;
  const delay = new Promise<void>(resolve => { release = resolve; });
  const acknowledgments: RichProjectResponse[] = [];
  const queue = new RichSaveQueue(initial, "session", async request => { await delay; return apply(initial, request); }, value => acknowledgments.push(value));
  queue.update(changed(initial, "Saved before switch"), "first");
  const pending = queue.flush(); queue.close(); release?.(); await pending;
  assert.equal(acknowledgments.length, 0);
});

test("a lost save reply retries the exact idempotency key before saving newer input", async () => {
  const initial = response(), sent: RichMutation[] = [];
  let accepted: RichProjectResponse | null = null;
  const queue = new RichSaveQueue(initial, "session", async request => {
    sent.push(request);
    if (sent.length === 1) { accepted = apply(initial, request); throw new Error("Connection lost"); }
    if (!accepted) throw new Error("Missing accepted reply");
    if (sent.length === 2) return accepted;
    accepted = apply(accepted, request); return accepted;
  }, () => {});
  queue.update(changed(initial, "Accepted edit"), "first");
  await assert.rejects(queue.flush(), /Connection lost/);
  queue.update(changed(initial, "Newer edit"), "second");
  await queue.flush();
  assert.equal(sent.length, 3);
  assert.deepEqual(sent[1], sent[0]);
  assert.notEqual(sent[2]?.clientMutationId, sent[0]?.clientMutationId);
});
