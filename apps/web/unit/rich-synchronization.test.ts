import assert from "node:assert/strict";
import test from "node:test";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import type { RichMutation } from "../src/contracts/generated/rich_mutation";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { documentCells, type StoredBlock } from "../src/rich/document-cells";
import { factCells, factsFromCells } from "../src/rich/fact-cells";
import { SessionHistory, type CellValue } from "../src/rich/history";
import { RichSaveQueue, type RichBlock } from "../src/rich/save-queue";
import { RichSynchronization } from "../src/rich/synchronization";

function initial(): RichProjectResponse {
  const workspace: unknown = structuredClone(fixture); assert.ok(validateRichWorkspaceShape(workspace));
  return { workspace, durability: "durable", savedProjectRevision: 1, savedDocumentRevision: 1, saveError: null, generation: null };
}

test("fact cells keep independent fields, retained date precision and tombstone-safe restoration", () => {
  const facts = initial().workspace.project?.facts; assert.ok(facts);
  const cells = factCells(facts), changed = structuredClone(facts), candidate = changed.records[0]; assert.ok(candidate?.kind === "candidate");
  candidate.name.rawText = candidate.name.value = "Sam"; candidate.name.userCorrected = true;
  const after = factCells(changed), differences = [...after].filter(([key, value]) => cells.get(key) !== value);
  assert.equal(differences.length, 1); assert.ok(differences[0]?.[0].startsWith("fact-field:"));
  const history = new SessionHistory("session", cells, changes => { changes.forEach(change => cells.set(change.key, change.after)); });
  history.commit("panel", differences.map(([key, value]) => ({ key, before: cells.get(key) ?? null, after: value })));
  const edited = factsFromCells(cells, facts); assert.equal(edited.records[0]?.kind, "candidate");
  const education = edited.records.find(record => record.kind === "education"); assert.ok(education?.kind === "education");
  assert.deepEqual(education.completion.value, { precision: "day", year: 2018, month: 5, day: 23 });
  assert.ok(history.undo()); assert.deepEqual(factCells(factsFromCells(cells, facts)), factCells(facts));
  assert.ok(history.redo()); assert.deepEqual(factCells(factsFromCells(cells, facts)), after);
});

for (const lateUndo of [false, true]) test(`delayed completion ${lateUndo ? "rejects undo/redo with equal text" : "attaches to its edit across unrelated typing"}`, async () => {
  let response = initial(); const project = response.workspace.project; assert.ok(project);
  const initialDocument = project.document, initialFacts = project.facts;
  const cache = new Map<string, StoredBlock>();
  const cells = (value: RichProjectResponse) => {
    const project = value.workspace.project; assert.ok(project);
    return new Map([...documentCells(project.document, cache), ...factCells(project.facts)]);
  };
  let current: Map<string, CellValue> = cells(response);
  function document() {
    const rebuild = (id: string): RichBlock => { const json = current.get(`block:${id}`), stored = json ? cache.get(json) : undefined;
      assert.ok(stored); return { ...stored.block, children: stored.children.map(rebuild) }; };
    const regions = initialDocument.regions.map(region => {
      const value: unknown = JSON.parse(current.get(`region:${region.id}`) ?? "[]");
      assert.ok(Array.isArray(value) && value.every((id: unknown) => typeof id === "string"));
      return { ...region, blocks: value.map((id: string) => rebuild(id)) };
    });
    const [header, sidebar, main] = regions; assert.ok(header && sidebar && main);
    return { ...initialDocument, regions: [header, sidebar, main] as [typeof header, typeof sidebar, typeof main] };
  }
  const history = new SessionHistory("session", current, changes => { current = new Map(current); changes.forEach(change => current.set(change.key, change.after)); });
  function publish() { queue.update(document(), history.currentActionId ?? "session", "typing", factsFromCells(current, initialFacts)); }
  function apply(base: RichProjectResponse, request: RichMutation): RichProjectResponse {
    const next = structuredClone(base), project = next.workspace.project; assert.ok(project);
    for (const step of request.steps) {
      if (step.kind === "put_record") {
        const index = project.facts.records.findIndex(record => record.id === step.record.id); assert.ok(index >= 0);
        project.facts.records[index] = structuredClone(step.record); project.facts.records[index].revision = (step.beforeRevision ?? 0) + 1;
      } else if (step.kind === "put_block") {
        for (const region of project.document.regions) {
          const index = region.blocks.findIndex(block => block.id === step.block.id);
          if (index >= 0) region.blocks[index] = { ...structuredClone(step.block), revision: (step.beforeRevision ?? 0) + 1 };
        }
      } else assert.fail("Unexpected test mutation");
    }
    return next;
  }
  const queue = new RichSaveQueue(response, "session", async request => { response = apply(response, request); return response; }, () => {});
  let finish: (() => void) | undefined, started: (() => void) | undefined;
  const held = new Promise<void>(resolve => { finish = resolve; }), ready = new Promise<void>(resolve => { started = resolve; });
  let disposition = "", previewCount = 0;
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    const path = String(input);
    if (path.endsWith("/completion")) {
      started?.(); await held;
      const candidate = structuredClone(project.facts.records[0]); assert.ok(candidate?.kind === "candidate");
      candidate.title.rawText = candidate.title.value = "Senior Engineer"; candidate.title.userCorrected = true; candidate.userCorrected = true;
      response.workspace.syncRecords.push({ id: "sync-test", status: "pending", kind: "completion", actionId: "session:1", blockIds: ["title"],
        factIds: [candidate.id], fieldKeys: ["title"], dependencies: [], errorCode: null, ready: true,
        proposedSteps: [{ kind: "put_record", beforeRevision: 1, record: candidate }] });
    } else if (path.endsWith("/preview")) {
      previewCount++;
      const body: unknown = JSON.parse(String(init?.body)); assert.ok(typeof body === "object" && body !== null && "steps" in body && Array.isArray(body.steps));
      const next = structuredClone(response), candidate = next.workspace.project?.facts.records[0]; assert.ok(candidate?.kind === "candidate");
      candidate.title.rawText = candidate.title.value = "Senior Engineer"; candidate.title.userCorrected = true; candidate.userCorrected = true;
      return Response.json(next);
    } else if (path.endsWith("/sync/sync-test")) {
      const body: unknown = JSON.parse(String(init?.body)); assert.ok(typeof body === "object" && body !== null && "status" in body && typeof body.status === "string");
      disposition = body.status; const sync = response.workspace.syncRecords[0]; assert.ok(sync); sync.status = disposition === "applied" ? "applied" : "stale";
    }
    return Response.json(response);
  };
  try {
    const sync = new RichSynchronization({ history, queue, current: () => current, cells, changed: publish, report: () => {} }, response.workspace.projectId);
    function edit(id: string, text: string) {
      const doc = structuredClone(document()), block = doc.regions[0]?.blocks.find(block => block.id === id); assert.ok(block && Array.isArray(block.content));
      const span = block.content[0]; assert.ok(span && span.type !== "link"); span.text = text;
      const next = documentCells(doc, cache), key = `block:${id}`;
      const action = history.commit("typing", [{ key, before: current.get(key) ?? null, after: next.get(key) ?? null }]); assert.ok(action); publish(); return action;
    }
    const action = edit("title", "Senior Engineer"), pending = sync.complete(action, ["title"], [], []);
    await ready;
    if (lateUndo) { assert.ok(history.undo()); assert.ok(history.redo()); publish(); }
    else edit("name", "Unrelated typing");
    finish?.(); await pending;
    const candidate = factsFromCells(current, initialFacts).records[0]; assert.ok(candidate?.kind === "candidate");
    assert.equal(candidate.title.value, lateUndo ? "Engineer" : "Senior Engineer");
    assert.equal(disposition, lateUndo ? "stale" : "applied"); assert.equal(previewCount, lateUndo ? 0 : 1);
    if (!lateUndo) {
      assert.ok(history.undo()); publish(); assert.ok(history.undo()); publish();
      const undone = factsFromCells(current, initialFacts).records[0]; assert.ok(undone?.kind === "candidate"); assert.equal(undone.title.value, "Engineer");
      assert.equal(document().regions[0]?.blocks[1]?.id, "title");
      assert.ok(history.redo()); publish(); assert.ok(history.redo()); publish();
      const redone = factsFromCells(current, initialFacts).records[0]; assert.ok(redone?.kind === "candidate"); assert.equal(redone.title.value, "Senior Engineer");
    }
    sync.close(); queue.close(); history.close();
  } finally { globalThis.fetch = realFetch; }
});

test("equivalent model text runs do not create a new editor action or save after acknowledgment", () => {
  const response = initial(), document = response.workspace.project?.document; assert.ok(document);
  const original = structuredClone(document), block = document.regions[0].blocks[0]; assert.ok(block && Array.isArray(block.content));
  const first = block.content[0]; assert.ok(first?.type === "text");
  block.content = [{ ...first, text: "Alex " }, { ...first, text: "Example" }];
  assert.deepEqual(documentCells(original, new Map()), documentCells(document, new Map()));
});
