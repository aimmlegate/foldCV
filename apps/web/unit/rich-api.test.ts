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
