import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import fixture from "../../../tests/fixtures/rich_workspace.json" with { type: "json" };
import type { RichProjectResponse } from "../src/contracts/generated/rich_project_response";
import { validateRichWorkspaceShape } from "../src/rich/validate";
import { documentCells, type StoredBlock } from "../src/rich/document-cells";
import { factCells, factsFromCells } from "../src/rich/fact-cells";
import { SessionHistory, type CellValue } from "../src/rich/history";
import { RichSaveQueue, type RichBlock } from "../src/rich/save-queue";
import { RichSynchronization, type PanelCommand } from "../src/rich/synchronization";
import { IntentQueue } from "../src/rich/intent-queue";

const python = `import json,sys
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.rich_panel import RichPanelRequest,panel_mutation
from packages.resume_core.rich_mutations import apply_rich_mutation
x=json.load(open(sys.argv[1]));w=WorkspaceV6.model_validate(x['workspace'])
r=panel_mutation(w,RichPanelRequest.model_validate(x['body'])) if x['panel'] else RichMutation.model_validate(x['body'])
if r is not None: w,_=apply_rich_mutation(w,r)
print(w.model_dump_json(by_alias=True))`;

export function panelHarness(options: { preview?: (count: number) => Promise<void>; save?: (count: number) => Promise<void>; workspace?: unknown } = {}) {
  const directory = mkdtempSync(join(tmpdir(), "foldcv-panel-queue-")); let sequence = 0;
  const file = (value: unknown) => { const path = join(directory, `${++sequence}.json`); writeFileSync(path, JSON.stringify(value)); return path; };
  const raw: unknown = JSON.parse(execFileSync(".venv/bin/python", ["-c", "import sys;from pathlib import Path;from packages.resume_core.models.rich_workspace import WorkspaceV6;print(WorkspaceV6.model_validate_json(Path(sys.argv[1]).read_text()).model_dump_json(by_alias=True))", file(options.workspace ?? fixture)],
    { cwd: new URL("../../../", import.meta.url), encoding: "utf8", timeout: 5000 }));
  assert.ok(validateRichWorkspaceShape(raw));
  let response: RichProjectResponse = { workspace: raw, durability: "durable", savedProjectRevision: 1, savedDocumentRevision: 1, saveError: null, generation: null };
  const project = response.workspace.project; assert.ok(project); const baseline = project;
  const cache = new Map<string, StoredBlock>();
  const cells = (value: RichProjectResponse) => { const project = value.workspace.project; assert.ok(project);
    return new Map([...documentCells(project.document, cache), ...factCells(project.facts)]); };
  const current: Map<string, CellValue> = cells(response);
  function document() {
    const rebuild = (id: string): RichBlock => { const encoded = current.get(`block:${id}`), stored = encoded ? cache.get(encoded) : undefined; assert.ok(stored);
      return { ...stored.block, children: stored.children.map(rebuild) }; };
    const regions = baseline.document.regions.map(region => {
      const ids: unknown = JSON.parse(current.get(`region:${region.id}`) ?? "[]"); assert.ok(Array.isArray(ids));
      return { ...region, blocks: ids.map((id: unknown) => { assert.equal(typeof id, "string"); return rebuild(String(id)); }) };
    });
    const [header, sidebar, main] = regions; assert.ok(header && sidebar && main);
    return { ...baseline.document, regions: [header, sidebar, main] as [typeof header, typeof sidebar, typeof main] };
  }
  const history = new SessionHistory("queue-session", current, changes => { for (const change of changes) current.set(change.key, change.after); });
  function call(body: unknown, panel: boolean) {
    const value: unknown = JSON.parse(execFileSync(".venv/bin/python", ["-c", python, file({ workspace: response.workspace, body, panel })],
      { cwd: new URL("../../../", import.meta.url), encoding: "utf8", timeout: 5000 }));
    assert.ok(validateRichWorkspaceShape(value)); return { ...response, workspace: value };
  }
  let saves = 0, previews = 0;
  const queue = new RichSaveQueue(response, "queue-session", async request => { saves++; assert.ok(saves <= 15, "Save must settle"); await options.save?.(saves); response = call(request, false); return response; }, () => {});
  const publish = () => queue.update(document(), history.currentActionId ?? "queue-session", "panel", factsFromCells(current, baseline.facts));
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    if (String(input).endsWith("/panel/preview")) { const count = ++previews; await options.preview?.(count); return Response.json(call(JSON.parse(String(init?.body)) as unknown, true)); }
    return Response.json(response);
  };
  const sync = new RichSynchronization({ history, queue, current: () => current, cells, changed: publish, report: () => {} }, response.workspace.projectId);
  const intents = new IntentQueue<PanelCommand>(command => sync.panel(command), () => {});
  const facts = () => factsFromCells(current, baseline.facts);
  return { history, queue, sync, intents, publish, facts, current, document, previews: () => previews, saves: () => saves,
    technologies: (jobId: string | null = null) => facts().records.filter(record => record.kind === "technology" && record.jobId === jobId)
      .map(record => record.kind === "technology" ? record.display.rawText : ""),
    close: () => { sync.close(); intents.close(); history.close(); queue.close(); globalThis.fetch = originalFetch; rmSync(directory, { recursive: true, force: true }); } };
}
