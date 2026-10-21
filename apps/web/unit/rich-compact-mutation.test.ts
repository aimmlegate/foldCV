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

function byteLength(value: unknown): number { return Buffer.byteLength(JSON.stringify(value)); }
function sizedEdit(before: RichDocumentV1, bytes: number, character: string): RichDocumentV1 {
  const after = structuredClone(before), block = after.regions[0].blocks[0];
  assert.ok(block && Array.isArray(block.content));
  block.content = [{ type: "text", text: "x", styles: wireMarks({}) }];
  const probe = { ...compactMutation(mutation(before, after), before), clientMutationId: "00000000-0000-4000-8000-000000000000" };
  const available = bytes - byteLength(probe) + 1, width = Buffer.byteLength(character);
  const span = block.content[0]; assert.ok(span?.type === "text");
  span.text = character.repeat(Math.floor(available / width)) + "x".repeat(available % width);
  return after;
}

for (const character of ["x", "я", "🛠"]) for (const offset of [-1, 0, 1]) {
  test(`compacted ${character} saves enforce the UTF-8 byte boundary at 1 MiB ${offset >= 0 ? "+" : ""}${offset}`, async () => {
    const initial = baseline(), project = initial.workspace.project; assert.ok(project);
    const block = project.document.regions[0].blocks[0]; assert.ok(block); large(block);
    const expectedBytes = 1024 * 1024 + offset, after = sizedEdit(project.document, expectedBytes, character);
    let calls = 0;
    const queue = new RichSaveQueue(initial, "session", async request => {
      calls++;
      if (offset <= 0) assert.equal(byteLength(request), expectedBytes);
      else assert.ok(byteLength(request) < 10000);
      assert.equal(request.steps[0]?.kind, "replace_inline_range"); return apply(initial, request);
    }, () => {});
    queue.update(after, "edit", "panel");
    if (offset <= 0) {
      await queue.flush(); assert.equal(calls, 1);
      assert.deepEqual(documentSteps(queue.baseline.workspace.project?.document ?? after, after), []);
    } else {
      await assert.rejects(queue.flush(), /лимит 1 МБ/); assert.equal(calls, 0); assert.equal(queue.baseline, initial);
      const corrected = structuredClone(project.document), target = corrected.regions[0].blocks[0];
      assert.ok(target && Array.isArray(target.content)); target.content = [{ type: "text", text: "Corrected", styles: wireMarks({}) }];
      queue.update(corrected, "corrected"); await queue.flush(); assert.equal(calls, 1);
      assert.deepEqual(documentSteps(queue.baseline.workspace.project?.document ?? corrected, corrected), []);
    }
  });
}

for (const count of [1000, 1001]) {
  test(`${count} fact removals respect the atomic step ceiling`, async () => {
    const initial = baseline(), project = initial.workspace.project; assert.ok(project);
    const education = project.facts.records.find(record => record.kind === "education"); assert.ok(education);
    const after = structuredClone(project.facts);
    project.facts.records.push(...Array.from({ length: count }, (_, index) => ({ ...structuredClone(education), id: `extra-${index}` })));
    let calls = 0;
    const queue = new RichSaveQueue(initial, "session", async request => {
      calls++; assert.equal(request.steps.length, count); return apply(initial, request);
    }, () => {});
    queue.update(project.document, "remove", "panel", after);
    if (count === 1000) { await queue.flush(); assert.equal(calls, 1); }
    else { await assert.rejects(queue.flush(), /слишком большое/); assert.equal(calls, 0); assert.equal(queue.baseline, initial); }
  });
}

test("compacted UTF-16 ranges replace links and fact spans without losing children or formatting", () => {
  const initial = baseline(), project = initial.workspace.project; assert.ok(project);
  const block = project.document.regions[0].blocks[0]; assert.ok(block?.type === "paragraph");
  block.content = [{ type: "text", text: "A🛠Б", styles: wireMarks({ bold: true }) },
    { type: "link", href: "https://example.com/old", content: [{ type: "text", text: "🔗x", styles: wireMarks({ italic: true }) }] },
    { type: "fact_field", bindingId: "save-binding", bindingRootId: "save-binding", recordId: "candidate-1", fieldKey: "name",
      syncedFactRevision: 1, text: "😀", styles: wireMarks({ underline: true }) }];
  block.children = [{ ...structuredClone(block), id: "retained-child", content: [], children: [] }];
  large(block);
  const after = structuredClone(project.document), changed = after.regions[0].blocks[0]; assert.ok(changed?.type === "paragraph");
  changed.content = [{ type: "link", href: "https://example.com/new", content: [{ type: "text", text: "Новый 🛠", styles: wireMarks({ bold: true, textColor: "#112233" }) }] }];
  const compact = compactMutation(mutation(project.document, after), project.document), step = compact.steps[0];
  assert.ok(step?.kind === "replace_inline_range"); assert.equal(step.end, 9);
  const actual = apply(initial, compact).workspace.project; assert.ok(actual);
  assert.deepEqual(documentSteps(actual.document, after), []);
  assert.deepEqual(actual.document.regions[0].blocks[0]?.children, block.children);
  assert.deepEqual(actual.document.regions[0].blocks[0]?.provenance, block.provenance);
});

for (const change of ["table-layout", "image-properties", "provenance"] as const) {
  test(`compaction retains whole-block ${change} edits`, () => {
    const initial = baseline(), project = initial.workspace.project; assert.ok(project);
    const after = structuredClone(project.document);
    if (change === "table-layout") {
      const table = after.regions[2].blocks.find(block => block.type === "table"); assert.ok(table?.type === "table");
      table.content.columnWidths[0] = 200;
      const cell = table.content.rows[0].cells[0]; assert.ok(cell);
      cell.content = [{ type: "text", text: "Layout and content", styles: wireMarks({}) }];
    } else if (change === "image-properties") {
      const image = after.regions[2].blocks.find(block => block.type === "image"); assert.ok(image?.type === "image");
      image.props.alt = "Updated alt"; image.props.caption = [{ type: "text", text: "Updated caption", styles: wireMarks({}) }];
    } else {
      const block = after.regions[0].blocks[0]; assert.ok(block && Array.isArray(block.content));
      block.provenance = [{ kind: "working_owner", id: "new-owner", recordId: "candidate-1" }];
      block.content = [{ type: "text", text: "New provenance", styles: wireMarks({}) }];
    }
    const request = mutation(project.document, after), compact = compactMutation(request, project.document);
    assert.deepEqual(compact, request);
    const actual = apply(initial, compact).workspace.project; assert.ok(actual);
    assert.deepEqual(documentSteps(actual.document, after), []);
  });
}

test("one character in a large resume sends one range and never includes the rest of the document", async () => {
  const initial = baseline(), project = initial.workspace.project; assert.ok(project);
  const block = project.document.regions[0].blocks[0]; assert.ok(block?.type === "paragraph"); large(block);
  const untouched = Array.from({ length: 120 }, (_, index) => ({ ...structuredClone(block), id: `untouched-${index}`,
    provenance: [], children: [], content: [{ type: "text" as const, text: `Unrelated section ${index}: ` + "z".repeat(10000), styles: wireMarks({}) }] }));
  project.document.regions[2].blocks.push(...untouched);
  assert.ok(byteLength(project.document) > 2 * 1024 * 1024);
  const after = structuredClone(project.document), edited = after.regions[0].blocks[0]; assert.ok(edited?.type === "paragraph");
  const span = edited.content[0]; assert.ok(span?.type === "text"); span.text += "!";
  let calls = 0;
  const queue = new RichSaveQueue(initial, "session", async request => {
    calls++; assert.equal(request.steps.length, 1); assert.ok(byteLength(request) < 2000);
    const step = request.steps[0]; assert.ok(step?.kind === "replace_inline_range"); assert.equal(step.blockId, block.id);
    const wire = JSON.stringify(request);
    for (const forbidden of ["untouched-", "Unrelated section", '"regions"', '"records"', '"provenance"', '"workspace"']) assert.ok(!wire.includes(forbidden), forbidden);
    return apply(initial, request);
  }, () => {});
  await queue.flush(); assert.equal(calls, 0);
  queue.update(after, "single-character"); await queue.flush(); assert.equal(calls, 1);
  assert.deepEqual(queue.baseline.workspace.project?.document.regions[2].blocks.slice(-120), untouched);
  assert.deepEqual(queue.baseline.workspace.project?.facts, project.facts);
  assert.deepEqual(documentSteps(queue.baseline.workspace.project?.document ?? after, after), []);
});

test("editing one nested paragraph sends no ancestor or sibling blocks", async () => {
  const initial = baseline(), project = initial.workspace.project; assert.ok(project);
  const after = structuredClone(project.document), section = after.regions[2].blocks.find(block => block.id === "job-section"); assert.ok(section);
  const edited = section.children.find(block => block.id === "narrative"); assert.ok(edited?.type === "paragraph");
  edited.content.push({ type: "text", text: "!", styles: wireMarks({}) });
  let calls = 0;
  const queue = new RichSaveQueue(initial, "session", async request => {
    calls++; assert.equal(request.steps.length, 1);
    const step = request.steps[0]; assert.ok(step?.kind === "put_block");
    assert.equal(step.block.id, "narrative"); assert.deepEqual(step.block.children, []); assert.equal(step.keepChildren, true);
    assert.ok(!JSON.stringify(request).includes('"regions"')); return apply(initial, request);
  }, () => {});
  queue.update(after, "nested"); await queue.flush(); assert.equal(calls, 1);
  assert.deepEqual(documentSteps(queue.baseline.workspace.project?.document ?? after, after), []);
});

test("editing one fact sends only that record without document blocks or other facts", async () => {
  const initial = baseline(), project = initial.workspace.project; assert.ok(project);
  const after = structuredClone(project.facts), candidate = after.records.find(record => record.kind === "candidate"); assert.ok(candidate);
  candidate.title.rawText = candidate.title.value = "Senior engineer";
  let calls = 0;
  const queue = new RichSaveQueue(initial, "session", async request => {
    calls++; assert.equal(request.steps.length, 1);
    const step = request.steps[0]; assert.ok(step?.kind === "put_record"); assert.equal(step.record.id, "candidate-1");
    const wire = JSON.stringify(request);
    for (const forbidden of ['"regions"', '"blocks"', '"records"', '"job-1"', '"education-1"']) assert.ok(!wire.includes(forbidden), forbidden);
    return apply(initial, request);
  }, () => {});
  queue.update(project.document, "one-fact", "panel", after); await queue.flush(); assert.equal(calls, 1);
  assert.deepEqual(factSteps(queue.baseline.workspace.project?.facts ?? after, after), []);
  assert.deepEqual(documentSteps(queue.baseline.workspace.project?.document ?? project.document, project.document), []);
});
