import assert from "node:assert/strict";
import test from "node:test";
import { download } from "../src/rich/api";

test("portable download sends only its captured revisions when passed a complete workspace", async () => {
  const original = globalThis.fetch;
  let captured: unknown;
  globalThis.fetch = async (_input, init) => {
    captured = typeof init?.body === "string" ? JSON.parse(init.body) : null;
    return new Response(new Uint8Array(22), { headers: { "Content-Type": "application/vnd.foldcv.project+zip" } });
  };
  try {
    const workspace = { schemaVersion: 6, projectId: "project", projectRevision: 3, documentRevision: 4, title: "Example" };
    const blob = await download("project", "archive", workspace);
    assert.equal(blob.size, 22);
    assert.deepEqual(captured, { projectRevision: 3, documentRevision: 4 });
  } finally { globalThis.fetch = original; }
});

test("project deletion validates its own result instead of a workspace and retains cleanup failures", async () => {
  const { deleteProject } = await import("../src/rich/api");
  const original = globalThis.fetch;
  let response: unknown = { projectId: "copy", status: "deleted", errorCode: null };
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "/v1/rich/projects/copy/delete");
    assert.deepEqual(JSON.parse(String(init?.body)) as unknown, { confirmed: true });
    return Response.json(response);
  };
  try {
    assert.deepEqual(await deleteProject("copy"), response);
    response = { projectId: "copy", status: "cleanup_incomplete", errorCode: "FILES_BUSY" };
    assert.deepEqual(await deleteProject("copy"), response);
    response = { workspace: {} };
    await assert.rejects(deleteProject("copy"), /INVALID_RESULT/);
  } finally { globalThis.fetch = original; }
});
