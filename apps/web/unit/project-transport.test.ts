import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { openFoldcv } from "../src/projects/api";
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

test("a V6 archive is refused by its code so the caller can open the old route", async () => {
  const fetcher: Fetcher = () => Promise.resolve(Response.json({ error: { code: "ARCHIVE_WORKSPACE_INVALID" } }, { status: 422 }));
  await assert.rejects(openFoldcv(new File(["v6"], "old.foldcv"), fetcher), (error: unknown) => error instanceof ProjectApiFailure && error.code === "ARCHIVE_WORKSPACE_INVALID");
});
