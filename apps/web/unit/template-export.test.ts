import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { templateExportArtifact } from "../src/contracts/template-export";
import type { TemplateSnapshotIdentity } from "../src/contracts/generated/template_snapshot_identity";
import type { TemplateProjectResponseV1 } from "../src/contracts/generated/template_project_response_v1";
import { ProjectApiFailure, ProjectEditorConnection } from "../src/rich/v7-connection";

const expected: TemplateSnapshotIdentity = { projectId: "synthetic-project", projectRevision: 3, documentRevision: 2,
  documentHash: "a".repeat(64), factsHash: "b".repeat(64), packageHash: "c".repeat(64), presentationHash: "d".repeat(64) };
const artifact = new TextEncoder().encode("controlled artifact; not a DOCX rendering claim");
const mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

async function headers(): Promise<Headers> {
  const hash = await crypto.subtle.digest("SHA-256", artifact);
  return new Headers({ "Content-Type": mime, "X-FoldCV-Export-Attempt": "synthetic-export",
    "X-FoldCV-Snapshot": JSON.stringify(expected),
    "X-FoldCV-Sha256": Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("") });
}

test("an export returns exact captured snapshot, opaque attempt and verified bytes", async () => {
  const result = await templateExportArtifact(new Response(artifact, { headers: await headers() }), expected);
  assert.equal(result.attemptId, "synthetic-export");
  assert.deepEqual(result.snapshot, expected);
  assert.equal(await result.blob.text(), new TextDecoder().decode(artifact));
});

test("every snapshot field and required success header rejects a different capture", async () => {
  for (const key of Object.keys(expected) as (keyof TemplateSnapshotIdentity)[]) {
    const changed = { ...expected, [key]: typeof expected[key] === "number" ? 99 : "e".repeat(64) };
    const fields = await headers(); fields.set("X-FoldCV-Snapshot", JSON.stringify(changed));
    await assert.rejects(templateExportArtifact(new Response(artifact, { headers: fields }), expected), /INVALID_RESULT/, key);
  }
  for (const key of ["Content-Type", "X-FoldCV-Export-Attempt", "X-FoldCV-Snapshot"]) {
    const fields = await headers(); fields.delete(key);
    await assert.rejects(templateExportArtifact(new Response(artifact, { headers: fields }), expected), /INVALID_RESULT/, key);
  }
  await assert.rejects(templateExportArtifact(new Response(artifact, { headers: await headers() }), expected, "another-export"), /INVALID_RESULT/);
});

test("unsafe, extra and missing snapshot values cannot reuse a claimed identity", async () => {
  for (const source of [JSON.stringify({ ...expected, projectRevision: Number.MAX_SAFE_INTEGER + 1 }), JSON.stringify({ ...expected, extra: true }),
    "null", "{}", "[]", "not json"]) {
    const fields = await headers(); fields.set("X-FoldCV-Snapshot", source);
    await assert.rejects(templateExportArtifact(new Response(artifact, { headers: fields }), expected));
  }
});

test("missing or changed byte hashes and empty bodies reject adoption", async () => {
  for (const hash of [null, "0".repeat(64), "not-a-hash"]) {
    const fields = await headers();
    if (hash === null) fields.delete("X-FoldCV-Sha256"); else fields.set("X-FoldCV-Sha256", hash);
    await assert.rejects(templateExportArtifact(new Response(artifact, { headers: fields }), expected), /ARTIFACT_BYTES_MISMATCH/);
  }
  await assert.rejects(templateExportArtifact(new Response(new Uint8Array(), { headers: await headers() }), expected), /INVALID_RESULT/);
});

test("an oversized stream stops at the artifact boundary and cancels its reader", async () => {
  let cancelled = false;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) { controller.enqueue(new Uint8Array(1024 * 1024)); },
    cancel() { cancelled = true; },
  });
  await assert.rejects(templateExportArtifact(new Response(stream, { headers: await headers() }), expected), /INVALID_RESULT/);
  assert.ok(cancelled);
});

test("an artifact at the exact size boundary is accepted when its bytes match", async () => {
  const bytes = new Uint8Array(32 * 1024 * 1024);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  const fields = await headers();
  fields.set("X-FoldCV-Sha256", Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join(""));
  const result = await templateExportArtifact(new Response(bytes, { headers: fields }), expected);
  assert.equal(result.blob.size, bytes.byteLength);
});

test("the export request preserves a server failure without consuming it as an artifact", async () => {
  const base = JSON.parse(readFileSync(new URL("../../../tests/fixtures/synthetic/projects/v7-response.json", import.meta.url), "utf8")) as TemplateProjectResponseV1;
  const editor = new ProjectEditorConnection(base.workspace.projectId, "editor-token", base, { undo: null, redo: null },
    () => Promise.resolve(Response.json({ error: { code: "IMPORT_EXPORT_SNAPSHOT_STALE" } }, { status: 409 })));
  await assert.rejects(editor.exportDocx(), (error: unknown) => error instanceof ProjectApiFailure
    && error.code === "IMPORT_EXPORT_SNAPSHOT_STALE" && error.status === 409);
});
