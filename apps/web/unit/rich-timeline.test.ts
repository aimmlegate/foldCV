import assert from "node:assert/strict";
import test from "node:test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { documentCells, type StoredBlock } from "../src/rich/document-cells";
import { factCells, factsFromCells } from "../src/rich/fact-cells";
import { SessionHistory, type CellValue } from "../src/rich/history";
import { RichSaveQueue, type RichBlock } from "../src/rich/save-queue";
import { RichSynchronization } from "../src/rich/synchronization";
import { dateAnchors } from "../src/rich/date-edit";

const python = `import sys,json
from pathlib import Path
from pydantic import TypeAdapter
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.models.rich_document import RichBlock
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.rich_panel import RichPanelRequest,panel_mutation,record_blocks
from packages.resume_core.rich_timeline import CascadeRequest,CascadeApplyRequest,cascade_proposal,cascade_mutation
from packages.resume_core.rich_mutations import apply_rich_mutation
from tests.recovery.test_rich_timeline import timeline
x=json.loads(Path(sys.argv[1]).read_text());mode=x['mode']
if mode=='initial':
 w=timeline([('A','a','2020-01','2020-03'),('B','b','2020-04','2020-06')])
 for r in w.project.facts.records:
  if r.kind=='employment':w.project.document.regions[2].blocks.extend(TypeAdapter(RichBlock).validate_python(b) for b in record_blocks(r))
else:w=WorkspaceV6.model_validate(x['workspace'])
if mode=='proposal':print(cascade_proposal(w,CascadeRequest.model_validate(x['body'])).model_dump_json(by_alias=True));sys.exit()
if mode in ['panel','cascade','save']:
 r=panel_mutation(w,RichPanelRequest.model_validate(x['body'])) if mode=='panel' else cascade_mutation(w,CascadeApplyRequest.model_validate(x['body'])) if mode=='cascade' else RichMutation.model_validate(x['body'])
 w,_=apply_rich_mutation(w,r)
print(w.model_dump_json(by_alias=True))`;
for (const stale of [false, true]) test(`cascade ${stale ? "rejects a preview after equal-text undo redo" : "is one undo action and preserves unrelated prose and the date edit"}`, { timeout: 20000 }, async context => {
  const directory = mkdtempSync(join(tmpdir(), "foldcv-timeline-")); context.after(() => rmSync(directory, { recursive: true, force: true }));
  let sequence = 0;
  function call(mode: string, workspace?: unknown, body?: unknown): unknown {
    const path = join(directory, `${++sequence}.json`); writeFileSync(path, JSON.stringify({ mode, workspace, body }));
    return JSON.parse(execFileSync(".venv/bin/python", ["-c", python, path], { cwd: new URL("../../../", import.meta.url), encoding: "utf8", timeout: 5000 })) as unknown;
  }
  const raw = call("initial"); assert.ok(validateRichWorkspaceShape(raw));
  let response: RichProjectResponse = { workspace: raw, durability: "durable", savedProjectRevision: 1, savedDocumentRevision: 1, saveError: null, generation: null };
  const requiredProject = (value: RichProjectResponse) => { const project = value.workspace.project; assert.ok(project); return project; };
  const project = requiredProject(response);
  const cache = new Map<string, StoredBlock>();
  const cells = (value: RichProjectResponse) => { const project = value.workspace.project; assert.ok(project); return new Map([...documentCells(project.document, cache), ...factCells(project.facts)]); };
  const current: Map<string, CellValue> = cells(response);
  function document() {
    const rebuild = (id: string): RichBlock => { const value = current.get(`block:${id}`), item = value ? cache.get(value) : undefined; assert.ok(item); return { ...item.block, children: item.children.map(rebuild) }; };
    const regions = project.document.regions.map(region => { const ids: unknown = JSON.parse(current.get(`region:${region.id}`) ?? "[]"); assert.ok(Array.isArray(ids) && ids.every((id: unknown) => typeof id === "string")); return { ...region, blocks: ids.map((id: string) => rebuild(id)) }; });
    const [header, sidebar, main] = regions; assert.ok(header && sidebar && main); return { ...project.document, regions: [header, sidebar, main] as [typeof header, typeof sidebar, typeof main] };
  }
  const history = new SessionHistory("dates", current, changes => { changes.forEach(change => current.set(change.key, change.after)); });
  function evaluated(mode: string, body: unknown): RichProjectResponse { const workspace = call(mode, response.workspace, body); assert.ok(validateRichWorkspaceShape(workspace)); return { ...response, workspace }; }
  let sends = 0, applyCalls = 0, panelSyncs = 0;
  const queue = new RichSaveQueue(response, "dates", async body => { assert.ok(++sends <= 8); response = evaluated("save", body); return response; }, () => {});
  const publish = () => queue.update(document(), history.currentActionId ?? "dates", "cascade", factsFromCells(current, project.facts));
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    const path = String(input), body: unknown = init?.body ? JSON.parse(String(init.body)) : null;
    if (path.endsWith("/panel/sync")) panelSyncs++;
    if (path.endsWith("/panel/preview")) return Response.json(evaluated("panel", body));
    if (path.endsWith("/cascade/preview")) { applyCalls++; return Response.json(evaluated("cascade", body)); }
    if (path.endsWith("/cascade")) return Response.json(call("proposal", response.workspace, body));
    return Response.json(response);
  };
  const sync = new RichSynchronization({ history, queue, current: () => current, cells, changed: publish, report: () => {} }, response.workspace.projectId);
  const dates = () => factsFromCells(current, project.facts).records.filter(record => record.kind === "employment").map(record => record.periods.map(period => [period.start.rawText, period.end.rawText]));
  try {
    await sync.panel({ operation: "edit", recordId: "A", values: { "period:a:end": "2020-04" } });
    const action = history.currentActionId; assert.ok(action);
    const proposal = await sync.cascadePreview("A", "a", action); assert.equal(proposal.status, "available");
    if (stale) {
      assert.ok(history.undo()); publish(); assert.ok(history.redo()); publish(); await queue.flush();
      await assert.rejects(sync.cascadeApply(proposal), /устарел/); assert.equal(applyCalls, 0); assert.equal(panelSyncs, 1);
      assert.deepEqual(dates(), [[["2020-01", "2020-04"]], [["2020-04", "2020-06"]]]);
    } else {
      const doc = structuredClone(document()), name = doc.regions[0].blocks[0]; assert.ok(name && Array.isArray(name.content));
      const span = name.content[0]; assert.ok(span && span.type !== "link"); span.text = "Unrelated name";
      const next = documentCells(doc, cache), key = `block:${name.id}`;
      history.commit("typing", [{ key, before: current.get(key) ?? null, after: next.get(key) ?? null }]); publish();
      await sync.cascadeApply(proposal); assert.equal(history.position, 3); assert.equal(applyCalls, 1); assert.equal(panelSyncs, 2);
      assert.deepEqual(dates(), [[["2020-01", "2020-04"]], [["2020-05", "2020-07"]]]);
      assert.ok(history.undo()); publish(); await queue.flush();
      assert.deepEqual(dates(), [[["2020-01", "2020-04"]], [["2020-04", "2020-06"]]]);
      assert.ok(history.redo()); publish(); await queue.flush();
      assert.deepEqual(dates(), [[["2020-01", "2020-04"]], [["2020-05", "2020-07"]]]);
    }
  } finally { sync.close(); queue.close(); history.close(); globalThis.fetch = originalFetch; }
});

test("date anchors ignore correction metadata and retain the exact period ID", () => {
  const before = JSON.stringify({ value: null, rawText: "", userCorrected: false });
  const same = JSON.stringify({ value: null, rawText: "", userCorrected: true });
  const after = JSON.stringify({ value: { precision: "month", year: 2020, month: 4, day: null }, rawText: "2020-04", userCorrected: true });
  const key = 'fact-field:["job","period:period:with:colons:end"]';
  assert.deepEqual(dateAnchors("action", [{ key, before, after: same }]), []);
  assert.deepEqual(dateAnchors("action", [{ key, before, after }]), [{ jobId: "job", periodId: "period:with:colons", actionId: "action" }]);
});
