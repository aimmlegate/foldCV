import assert from "node:assert/strict";
import test from "node:test";
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
import { RichSynchronization } from "../src/rich/synchronization";

const python = `import json,sys
from packages.resume_core.models.rich_workspace import WorkspaceV6
from packages.resume_core.models.rich_mutations import RichMutation
from packages.resume_core.rich_panel import RichPanelRequest,panel_mutation
from packages.resume_core.rich_mutations import apply_rich_mutation
x=json.load(open(sys.argv[1]));w=WorkspaceV6.model_validate(x['workspace'])
r=panel_mutation(w,RichPanelRequest.model_validate(x['body'])) if x['panel'] else RichMutation.model_validate(x['body'])
w,_=apply_rich_mutation(w,r);print(w.model_dump_json(by_alias=True))`;
for (const mode of ["none", "related", "unrelated"] as const) test(`panel edit ${mode === "related" ? "rejects a late preview after newer typing" : mode === "unrelated" ? "keeps unrelated typing while a preview is pending" : "saves linked facts and text as one reversible action"}`, { timeout: 15000 }, async context => {
  const directory = mkdtempSync(join(tmpdir(), "foldcv-panel-"));
  context.after(() => rmSync(directory, { recursive: true, force: true }));
  let wireSequence = 0;
  const wireFile = (value: unknown) => { const path = join(directory, `${++wireSequence}.json`); writeFileSync(path, JSON.stringify(value)); return path; };
  const stale = mode === "related", delayed = mode !== "none";
  const raw: unknown = JSON.parse(execFileSync(".venv/bin/python", ["-c", "import sys;from pathlib import Path;from packages.resume_core.models.rich_workspace import WorkspaceV6;print(WorkspaceV6.model_validate_json(Path(sys.argv[1]).read_text()).model_dump_json(by_alias=True))", wireFile(fixture)],
    { cwd: new URL("../../../", import.meta.url), encoding: "utf8", timeout: 5000 })); assert.ok(validateRichWorkspaceShape(raw));
  let response: RichProjectResponse = { workspace: raw, durability: "durable", savedProjectRevision: 1, savedDocumentRevision: 1, saveError: null, generation: null };
  const requiredProject = (value: RichProjectResponse) => { const project = value.workspace.project; assert.ok(project); return project; };
  const baseline = requiredProject(response);
  const cache = new Map<string, StoredBlock>();
  const cells = (value: RichProjectResponse) => { const project = value.workspace.project; assert.ok(project);
    return new Map([...documentCells(project.document, cache), ...factCells(project.facts)]); };
  const current: Map<string, CellValue> = cells(response);
  function document() {
    const rebuild = (id: string): RichBlock => { const encoded = current.get(`block:${id}`), item = encoded ? cache.get(encoded) : undefined; assert.ok(item);
      return { ...item.block, children: item.children.map(rebuild) }; };
    const regions = baseline.document.regions.map(region => {
      const ids: unknown = JSON.parse(current.get(`region:${region.id}`) ?? "[]"); assert.ok(Array.isArray(ids) && ids.every((id: unknown) => typeof id === "string"));
      return { ...region, blocks: ids.map((id: string) => rebuild(id)) };
    });
    const [header, sidebar, main] = regions; assert.ok(header && sidebar && main);
    return { ...baseline.document, regions: [header, sidebar, main] as [typeof header, typeof sidebar, typeof main] };
  }
  const history = new SessionHistory("panel-session", current, changes => { changes.forEach(change => current.set(change.key, change.after)); });
  function call(body: unknown, panel: boolean): RichProjectResponse {
    const value: unknown = JSON.parse(execFileSync(".venv/bin/python", ["-c", python, wireFile({ workspace: response.workspace, body, panel })], { cwd: new URL("../../../", import.meta.url),
      encoding: "utf8", timeout: 5000 }));
    assert.ok(validateRichWorkspaceShape(value)); return { ...response, workspace: value };
  }
  let mutationCount = 0;
  const queue = new RichSaveQueue(response, "panel-session", async request => { assert.ok(++mutationCount <= 6, "Save must settle without repeated mutations"); response = call(request, false); return response; }, () => {});
  const publish = () => queue.update(document(), history.currentActionId ?? "panel-session", "panel", factsFromCells(current, baseline.facts));
  const originalFetch = globalThis.fetch;
  let release: (() => void) | undefined, admitted: (() => void) | undefined, syncCalls = 0;
  const held = new Promise<void>(resolve => { release = resolve; }), ready = new Promise<void>(resolve => { admitted = resolve; });
  globalThis.fetch = async (input, init) => {
    if (String(input).endsWith("/panel/preview")) {
      const result = call(JSON.parse(String(init?.body)) as unknown, true);
      admitted?.(); if (delayed) await held; return Response.json(result);
    }
    if (String(input).endsWith("/panel/sync")) syncCalls++;
    return Response.json(response);
  };
  const sync = new RichSynchronization({ history, queue, current: () => current, cells, changed: publish, report: () => {} }, response.workspace.projectId);
  try {
    const pending = sync.panel({ operation: "edit", recordId: "candidate-1", values: { title: "Senior Engineer" } });
    await Promise.race([ready, pending]);
    if (delayed) {
      const id = stale ? "title" : "name", key = `block:${id}`, value = current.get(key); assert.ok(value);
      const changed = JSON.parse(value) as unknown; assert.ok(typeof changed === "object" && changed !== null && "block" in changed);
      const doc = structuredClone(document()), block = doc.regions[0].blocks.find(block => block.id === id); assert.ok(block && Array.isArray(block.content));
      const span = block.content[0]; assert.ok(span && span.type !== "link"); span.text = "Newer title";
      const next = documentCells(doc, cache);
      history.commit("typing", [{ key, before: value, after: next.get(key) ?? null }]); publish(); release?.();
    }
    if (stale) {
      await assert.rejects(pending, /Повторите/); assert.equal(syncCalls, 0);
      assert.equal(factsFromCells(current, baseline.facts).records[0]?.kind, "candidate");
    } else {
      await pending; await queue.flush();
      const candidate = factsFromCells(current, baseline.facts).records[0]; assert.ok(candidate?.kind === "candidate"); assert.equal(candidate.title.value, "Senior Engineer");
      assert.equal(history.position, delayed ? 2 : 1); assert.equal(syncCalls, 1);
      if (delayed) { assert.ok(history.undo()); publish(); await queue.flush(); }
      assert.ok(history.undo()); publish(); await queue.flush();
      assert.deepEqual(factCells(factsFromCells(current, baseline.facts)), factCells(baseline.facts));
      assert.ok(history.redo()); publish(); await queue.flush();
      if (delayed) { assert.ok(history.redo()); publish(); await queue.flush(); }
      const redone = response.workspace.project?.facts.records[0]; assert.ok(redone?.kind === "candidate"); assert.equal(redone.title.value, "Senior Engineer");
    }
  } finally { sync.close(); queue.close(); history.close(); globalThis.fetch = originalFetch; }
});
