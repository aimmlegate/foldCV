import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import type { RichDocumentV1 } from "../src/contracts/generated/rich_document_v1";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import type { RichMutation } from "../src/contracts/generated/rich_mutation";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { validateRichDocumentShape } from "../src/rich/validate";
import { copyBlock, mergeBlocks } from "../src/rich/structure";
import { documentSteps, RichSaveQueue } from "../src/rich/save-queue";

function response(): RichProjectResponse {
  const workspace: unknown = structuredClone(fixture);
  assert.ok(validateRichWorkspaceShape(workspace));
  return { workspace, durability: "durable", savedProjectRevision: workspace.projectRevision,
    savedDocumentRevision: workspace.documentRevision, saveError: null, generation: null };
}

test("table save acknowledgments advance cell revisions without queuing the same content again", async () => {
  const baseline = response(), target = structuredClone(baseline.workspace.project?.document);
  assert.ok(target); const table = target.regions[2].blocks.find(block => block.type === "table");
  assert.ok(table && table.type === "table"); const cell = table.content.rows[0].cells[0]; assert.ok(cell);
  cell.content = [{ type: "text", text: "Edited table", styles: {} }];
  let calls = 0;
  const queue = new RichSaveQueue(baseline, "session", async request => {
    assert.equal(++calls, 1, "No repeated save after a revision-only acknowledgment");
    const step = request.steps[0]; assert.ok(step?.kind === "put_block" && step.block.type === "table");
    const next = structuredClone(baseline), project = next.workspace.project; assert.ok(project);
    const saved = structuredClone(step.block); assert.ok(saved.type === "table"); saved.revision++;
    for (const row of saved.content.rows) for (const cell of row.cells) cell.revision++;
    project.document.regions[2].blocks = project.document.regions[2].blocks.map(block => block.id === saved.id ? saved : block);
    return next;
  }, () => {});
  queue.update(target, "edit"); await queue.flush();
  assert.equal(calls, 1); assert.equal(documentSteps(queue.baseline.workspace.project?.document ?? target, target).length, 0);
});

test("a merged block promotes its existing children before Python removes their former parent", () => {
  const baseline = response(), project = baseline.workspace.project; assert.ok(project);
  const first = project.document.regions[0].blocks[0]; assert.ok(first);
  const child = copyBlock(first), source = { ...copyBlock(first), id: "source", type: "paragraph" as const, props: {},
    content: [{ type: "text" as const, text: "tail", styles: {} }], children: [child] };
  const target = { ...copyBlock(first), id: "target", type: "paragraph" as const, props: {}, content: [{ type: "text" as const, text: "head", styles: {} }], children: [] };
  project.document.regions[2].blocks.push(target, source);
  const expected = mergeBlocks(project.document, target.id, source.id), steps = documentSteps(project.document, expected);
  const leaf = (id: string) => ({ ...copyBlock(first), id, type: "paragraph" as const, props: {},
    content: [{ type: "text" as const, text: id, styles: {} }], children: [] });
  const mergedTarget = expected.regions[2].blocks.find(block => block.id === target.id); assert.ok(mergedTarget);
  expected.regions[2].blocks = [leaf("new-first"), ...expected.regions[2].blocks.filter(block => block.id !== target.id), leaf("new-before-target"), mergedTarget, leaf("new-last")];
  steps.splice(0, steps.length, ...documentSteps(project.document, expected));
  const repo = fileURLToPath(new URL("../../../", import.meta.url));
  const run = spawnSync(repo + ".venv/bin/python", ["-c", `import json,sys
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.rich_mutations import apply_rich_mutation
data=json.load(sys.stdin); w=WorkspaceV6.model_validate(data['workspace'])
m=RichMutation.model_validate({'schemaVersion':1,'projectId':w.project_id,'clientMutationId':'merge','actionId':'merge','kind':'structure','capture':{'sessionId':'session','actionId':'merge','actionToken':0,'dependencies':[]},'steps':data['steps']})
out,_=apply_rich_mutation(w,m); print(out.project.document.model_dump_json(by_alias=True))`],
  { cwd: repo, input: JSON.stringify({ workspace: baseline.workspace, steps }), encoding: "utf8", timeout: 5000 });
  assert.equal(run.status, 0, run.stderr);
  const actual: unknown = JSON.parse(run.stdout); assert.ok(validateRichDocumentShape(actual));
  const merged = actual.regions[2].blocks.find(block => block.id === target.id); assert.ok(merged && Array.isArray(merged.content));
  assert.equal(merged.children[0]?.id, child.id);
  assert.equal(merged.content.map(span => span.type === "link" ? span.content.map(part => part.text).join("") : span.text).join(""), "headtail");
  assert.ok(!actual.regions[2].blocks.some(block => block.id === source.id));
  assert.deepEqual(actual.regions[2].blocks.map(block => block.id), expected.regions[2].blocks.map(block => block.id));
});
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

test("a definitive rejected patch lets corrected input use a new key and preserves the save baseline", async () => {
  const initial = response(), sent: RichMutation[] = [];
  const queue = new RichSaveQueue(initial, "session", async request => {
    sent.push(request);
    if (sent.length === 1) throw Object.assign(new Error("Invalid patch"), { status: 422 });
    return apply(initial, request);
  }, () => {});
  queue.update(changed(initial, "Rejected input"), "first");
  await assert.rejects(queue.flush(), /Invalid patch/);
  assert.equal(queue.baseline, initial);
  queue.update(changed(initial, "Corrected input"), "second", "structure"); await queue.flush();
  assert.notEqual(sent[1]?.clientMutationId, sent[0]?.clientMutationId);
  assert.equal(sent[1]?.kind, "structure");
});
