import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import type { RichDocumentV1 } from "../src/contracts/generated/rich_document_v1";
import type { RichMutation } from "../src/contracts/generated/rich_mutation";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { compactMutation } from "../src/rich/compact-mutation";
import { wireMarks } from "../src/rich/inline";
import { documentSteps, factSteps, RichSaveQueue } from "../src/rich/save-queue";

type Block = RichDocumentV1["regions"][number]["blocks"][number];
function baseline(): RichProjectResponse {
  const repo = fileURLToPath(new URL("../../../", import.meta.url));
  const hydrated = spawnSync(repo + ".venv/bin/python", ["-c", "import json,sys; from packages.resume_core.models.rich_workspace import WorkspaceV6; print(WorkspaceV6.model_validate(json.load(sys.stdin)).model_dump_json(by_alias=True))"],
    { cwd: repo, input: JSON.stringify(fixture), encoding: "utf8", timeout: 5000 });
  assert.equal(hydrated.status, 0, hydrated.stderr);
  const workspace: unknown = JSON.parse(hydrated.stdout); assert.ok(validateRichWorkspaceShape(workspace));
  return { workspace, durability: "durable", savedProjectRevision: workspace.projectRevision,
    savedDocumentRevision: workspace.documentRevision, saveError: null, generation: null };
}
function large(block: Block): void {
  block.provenance = [{ kind: "source", id: "source-witness", evidence: [{ sourceId: "synthetic-source",
    sourceRevision: 1, unitId: "unit", unitRevision: 1, text: "x".repeat(1024 * 1024) }] }];
}
function mutation(before: RichDocumentV1, after: RichDocumentV1): RichMutation {
  const [first, ...rest] = documentSteps(before, after); assert.ok(first);
  return { schemaVersion: 1, projectId: "project-1", clientMutationId: "compact", actionId: "edit", kind: "panel",
    capture: { sessionId: "session", actionId: "edit", actionToken: 0, dependencies: [] }, steps: [first, ...rest] };
}
function apply(before: RichProjectResponse, request: RichMutation): RichProjectResponse {
  const repo = fileURLToPath(new URL("../../../", import.meta.url));
  const result = spawnSync(repo + ".venv/bin/python", ["-c", `import json,sys
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.rich_mutations import apply_rich_mutation
x=json.load(sys.stdin); w=WorkspaceV6.model_validate(x['workspace'])
w,_=apply_rich_mutation(w,RichMutation.model_validate(x['request']))
print(w.model_dump_json(by_alias=True))`], { cwd: repo, input: JSON.stringify({ workspace: before.workspace, request }),
    encoding: "utf8", timeout: 10000, maxBuffer: 10 * 1024 * 1024 });
  assert.equal(result.status, 0, result.stderr);
  const workspace: unknown = JSON.parse(result.stdout); assert.ok(validateRichWorkspaceShape(workspace));
  return { ...before, workspace };
}

test("oversized block and fact edits save atomically and retry the exact compact request", async () => {
  const initial = baseline(), project = initial.workspace.project; assert.ok(project);
  const block = project.document.regions[0].blocks[0]; assert.ok(block && Array.isArray(block.content)); large(block);
  const after = structuredClone(project.document), target = after.regions[0].blocks[0]; assert.ok(target && Array.isArray(target.content));
  target.content = [{ type: "text", text: "Engineer 🛠", styles: wireMarks({ bold: true }) }];
  const facts = structuredClone(project.facts), candidate = facts.records.find(record => record.kind === "candidate"); assert.ok(candidate);
  candidate.title.rawText = "Senior engineer"; candidate.title.value = "Senior engineer";
  assert.ok(Buffer.byteLength(JSON.stringify(mutation(project.document, after))) > 1024 * 1024);
  let saved: RichProjectResponse | null = null;
  const sent: RichMutation[] = [];
  const queue = new RichSaveQueue(initial, "session", async request => {
    sent.push(request); assert.ok(Buffer.byteLength(JSON.stringify(request)) < 10000);
    assert.equal(request.steps[0]?.kind, "replace_inline_range"); assert.equal(request.steps[1]?.kind, "put_record");
    if (!saved) { saved = apply(initial, request); throw new Error("Lost reply"); }
    return saved;
  }, () => {});
  queue.update(after, "edit", "panel", facts);
  await assert.rejects(queue.flush(), /Lost reply/); await queue.flush();
  assert.equal(sent.length, 2); assert.deepEqual(sent[1], sent[0]);
  assert.deepEqual(documentSteps(queue.baseline.workspace.project?.document ?? after, after), []);
  assert.deepEqual(factSteps(queue.baseline.workspace.project?.facts ?? facts, facts), []);
  assert.deepEqual(queue.baseline.workspace.project?.document.regions[0].blocks[0]?.provenance, block.provenance);
});

test("table cells and image captions compact while retaining layout children and styled UTF-16 text", () => {
  const initial = baseline(), project = initial.workspace.project; assert.ok(project);
  const after = structuredClone(project.document);
  const table = after.regions[2].blocks.find(block => block.type === "table"), image = after.regions[2].blocks.find(block => block.type === "image");
  assert.ok(table?.type === "table" && image?.type === "image");
  const cell = table.content.rows[0].cells[0]; assert.ok(cell);
  cell.content = [{ type: "text", text: "Технология 🛠", styles: wireMarks({ italic: true, textColor: "#112233" }) }];
  image.props.caption = [{ type: "text", text: "Caption 🛠", styles: wireMarks({ underline: true }) }];
  const compact = compactMutation(mutation(project.document, after), project.document);
  assert.deepEqual(compact.steps.map(step => step.kind), ["replace_inline_range", "replace_inline_range"]);
  const result = apply(initial, compact); assert.ok(result.workspace.project);
  assert.deepEqual(documentSteps(result.workspace.project.document, after), []);
  assert.deepEqual(result.workspace.project.document.regions[2].blocks[0], project.document.regions[2].blocks[0]);
});

test("compaction retains structural and metadata changes", () => {
  const initial = baseline(), project = initial.workspace.project; assert.ok(project);
  const after = structuredClone(project.document), block = after.regions[0].blocks[0];
  assert.ok(block?.type === "paragraph"); block.props.alignment = "right";
  after.regions[0].blocks.reverse();
  const request = mutation(project.document, after);
  assert.deepEqual(compactMutation(request, project.document), request);
});

test("a genuinely oversized structural edit fails before sending and preserves the baseline", async () => {
  const initial = baseline(), project = initial.workspace.project; assert.ok(project);
  const after = structuredClone(project.document), block = after.regions[0].blocks[0]; assert.ok(block?.type === "paragraph");
  large(block); block.props.alignment = "right";
  let calls = 0;
  const queue = new RichSaveQueue(initial, "session", async () => { calls++; return initial; }, () => {});
  queue.update(after, "large", "structure"); await assert.rejects(queue.flush(), /лимит 1 МБ/);
  assert.equal(calls, 0); assert.equal(queue.baseline, initial);
});
