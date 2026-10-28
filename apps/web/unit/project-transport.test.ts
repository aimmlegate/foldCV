import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { catalogFlag, createProject, deleteProject, listProjects, openFoldcv, parseTemplateCatalog, templateImportStatus } from "../src/projects/api";
import { ProjectApiFailure, ProjectEditorConnection, type Fetcher } from "../src/rich/v7-connection";

const base = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/projects/v7-response.json", import.meta.url), "utf8")) as TemplateProjectResponseV1;
const docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const foldcv = "application/vnd.foldcv.project+zip";
const bytes = new TextEncoder().encode("synthetic-file");

async function sha256(payload: Uint8Array<ArrayBuffer>): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", payload);
  return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
}

function connection(fetcher: Fetcher): ProjectEditorConnection {
  return new ProjectEditorConnection(base.workspace.projectId, "editor-token", structuredClone(base), { undo: null, redo: null }, fetcher);
}

test("rename, export and .foldcv use the open editor token and the current revisions", async () => {
  const calls: { path: string; body: Record<string, unknown> }[] = [];
  const renamed = structuredClone(base);
  renamed.workspace.projectRevision = 2;
  renamed.workspace.title = "Renamed";
  renamed.identity = { ...(renamed.identity ?? { title: "", subtitle: "" }), title: "Renamed" };
  const fetcher: Fetcher = async (path, init) => {
    calls.push({ path, body: JSON.parse(String(init?.body)) as Record<string, unknown> });
    if (path.endsWith("/rename")) return Response.json(renamed);
    if (path.endsWith("/export")) {
      const snapshot = (JSON.parse(String(init?.body)) as { snapshot: unknown }).snapshot;
      return new Response(bytes, { headers: { "Content-Type": docx, "X-FoldCV-Export-Attempt": "attempt-1",
        "X-FoldCV-Snapshot": JSON.stringify(snapshot), "X-FoldCV-Sha256": await sha256(bytes) } });
    }
    return new Response(bytes, { headers: { "Content-Type": foldcv } });
  };
  const editor = connection(fetcher);
  const snapshot = structuredClone(editor.response.snapshot);
  assert.ok(snapshot);
  assert.equal((await editor.rename("Renamed")).workspace.title, "Renamed");
  assert.equal(editor.response.workspace.projectRevision, 2);
  const exported = await editor.exportDocx();
  assert.equal(exported.attemptId, "attempt-1");
  assert.equal(await exported.blob.text(), "synthetic-file");
  const saved = await editor.saveFoldcv();
  assert.equal(saved.type, foldcv);
  assert.equal(await saved.text(), "synthetic-file");
  assert.deepEqual(calls.map(call => call.path.split("/").at(-1)), ["rename", "export", "archive"]);
  assert.deepEqual(calls[0]?.body, { editorToken: "editor-token", baseRevision: 1, title: "Renamed" });
  assert.equal(calls[1]?.body["schemaVersion"], 1);
  assert.equal(calls[1]?.body["editorToken"], "editor-token");
  assert.deepEqual(calls[1]?.body["snapshot"], snapshot);
  assert.deepEqual(calls[2]?.body, { editorToken: "editor-token", projectRevision: 2, documentRevision: 1 });
});

test("a refused archive keeps its code and an older workspace is not opened", async () => {
  const refused: Fetcher = () => Promise.resolve(Response.json({ error: { code: "ARCHIVE_WORKSPACE_INVALID" } }, { status: 422 }));
  await assert.rejects(openFoldcv(new File(["v6"], "old.foldcv"), refused), (error: unknown) => error instanceof ProjectApiFailure && error.code === "ARCHIVE_WORKSPACE_INVALID");
  const older = structuredClone(base) as unknown as { workspace: { schemaVersion: number } };
  older.workspace.schemaVersion = 6;
  await assert.rejects(openFoldcv(new File(["v6"], "old.foldcv"), () => Promise.resolve(Response.json(older, { status: 201 }))), /INVALID_RESULT/);
});

test("listing, creation, catalog flags and deletion use the kept routes", async () => {
  const calls: { path: string; method: string; body: unknown }[] = [];
  const listing = { entries: [{ projectId: "p", title: "T", updatedAt: "2026-10-27T00:00:00Z", tombstoned: false, cleanupStatus: "none",
    lastOpenedAt: null, archived: false }], errors: [] };
  const fetcher: Fetcher = (path, init) => {
    calls.push({ path, method: init.method ?? "GET", body: init.body instanceof FormData ? [...init.body.keys()] : init.body ? JSON.parse(String(init.body)) as unknown : null });
    if (path === "/v2/projects") return Promise.resolve(Response.json(listing));
    if (path.includes("/template-input")) return Promise.resolve(Response.json(base, { status: 201 }));
    if (init.method === "DELETE") return Promise.resolve(Response.json({ projectId: "p", cleanupStatus: "failed" }));
    return Promise.resolve(Response.json({ projectId: "p", archived: true }));
  };
  assert.deepEqual(await listProjects(fetcher), listing);
  const body = new FormData(); body.append("paste", new Blob(["text"]), "pasted.txt");
  assert.equal((await createProject(body, null, fetcher)).workspace.projectId, base.workspace.projectId);
  await createProject(body, "my cv/2", fetcher);
  await catalogFlag("p", true, fetcher);
  assert.equal((await deleteProject("p", fetcher)).cleanupStatus, "failed");
  assert.deepEqual(calls, [
    { path: "/v2/projects", method: "GET", body: null },
    { path: "/v1/rich/projects/template-input", method: "POST", body: ["paste"] },
    // A chosen template is a path segment: the service refuses query strings.
    { path: "/v1/rich/projects/template-input/my%20cv%2F2", method: "POST", body: ["paste"] },
    { path: "/v2/projects/p/catalog/archive", method: "POST", body: {} },
    { path: "/v2/projects/p", method: "DELETE", body: { confirmed: true } },
  ]);
});

test("the template list is checked before the import form offers it", async () => {
  const entry = { id: "generic", name: "Generic", revision: "2.6.0", packageHash: "a".repeat(64), bundled: true, edited: false };
  const reply = (value: unknown): Fetcher => () => Promise.resolve(Response.json(value));
  const status = { schemaVersion: 1, available: false, defaultId: "generic", templates: [entry] };
  assert.deepEqual(await templateImportStatus(reply(status)), { available: false, defaultId: "generic", templates: [entry] });
  for (const broken of [{ ...status, defaultId: "missing" }, { ...status, available: undefined },
    { ...status, templates: [{ ...entry, edited: "no" }] }, { ...status, schemaVersion: 2 }])
    await assert.rejects(templateImportStatus(reply(broken)), /INVALID_RESULT/);
  assert.deepEqual(parseTemplateCatalog({ schemaVersion: 1, defaultId: "generic", templates: [entry] }), { defaultId: "generic", templates: [entry] });
});
