import type { TemplateSnapshotIdentity } from "./generated/template_snapshot_identity";

const snapshotFields = ["projectId", "projectRevision", "documentRevision", "documentHash", "factsHash", "packageHash", "presentationHash"] as const;
const maximum = 32 * 1024 * 1024;
const mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/** The reply names the snapshot it rendered; it must be exactly the one the editor sent. */
function sameSnapshot(value: unknown, captured: TemplateSnapshotIdentity): value is TemplateSnapshotIdentity {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const keys = Object.keys(value);
  return keys.length === snapshotFields.length && snapshotFields.every(key => Reflect.get(value, key) === captured[key]);
}

async function boundedArtifact(response: Response): Promise<Blob> {
  if (!response.body) throw new Error("INVALID_RESULT");
  const reader = response.body.getReader(), chunks: ArrayBuffer[] = [];
  let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximum) throw new Error("INVALID_RESULT");
      const buffer = new ArrayBuffer(value.byteLength);
      new Uint8Array(buffer).set(value);
      chunks.push(buffer);
    }
    if (!size) throw new Error("INVALID_RESULT");
  } catch (error) {
    await reader.cancel().catch(() => undefined);
    throw error;
  } finally { reader.releaseLock(); }
  return new Blob(chunks, { type: mime });
}

export async function templateExportArtifact(response: Response, expected: TemplateSnapshotIdentity, expectedAttempt?: string):
Promise<{ blob: Blob; attemptId: string; snapshot: TemplateSnapshotIdentity }> {
  const captured = structuredClone(expected);
  if (!response.ok || response.headers.get("Content-Type") !== mime
      || !Number.isSafeInteger(captured.projectRevision) || !Number.isSafeInteger(captured.documentRevision)) throw new Error("INVALID_RESULT");
  const attemptId = response.headers.get("X-FoldCV-Export-Attempt"), source = response.headers.get("X-FoldCV-Snapshot");
  if (!attemptId || source === null || expectedAttempt !== undefined && attemptId !== expectedAttempt) throw new Error("INVALID_RESULT");
  let snapshot: unknown = null;
  try { snapshot = JSON.parse(source); } catch { throw new Error("INVALID_RESULT"); }
  if (!sameSnapshot(snapshot, captured)) throw new Error("INVALID_RESULT");
  const blob = await boundedArtifact(response);
  const hash = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  const sha256 = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
  if (sha256 !== response.headers.get("X-FoldCV-Sha256")) throw new Error("ARTIFACT_BYTES_MISMATCH");
  return { blob, attemptId, snapshot };
}
