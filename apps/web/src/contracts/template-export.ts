import Ajv2020 from "ajv/dist/2020.js";
import snapshotSchema from "../../../../contracts/json-schema/template_snapshot_identity.schema.json" with { type: "json" };
import type { TemplateSnapshotIdentity } from "./generated/template_snapshot_identity";
import { decodeJsonResponse } from "./json-response";

const snapshotShape = new Ajv2020({ strict: false }).compile<TemplateSnapshotIdentity>(snapshotSchema);
const snapshotFields = ["projectId", "projectRevision", "documentRevision", "documentHash", "factsHash", "packageHash", "presentationHash"] as const;
const maximum = 32 * 1024 * 1024;
const mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export type ReadCapture = Readonly<{ projectId: string; selectionEpoch: number; requestId: number }>;

export function readCaptureCurrent(captured: ReadCapture, current: ReadCapture): boolean {
  return captured.projectId === current.projectId && captured.selectionEpoch === current.selectionEpoch && captured.requestId === current.requestId;
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
  if (!response.ok || response.headers.get("Content-Type") !== mime || !snapshotShape(captured)
      || !Number.isSafeInteger(captured.projectRevision) || !Number.isSafeInteger(captured.documentRevision)) throw new Error("INVALID_RESULT");
  const attemptId = response.headers.get("X-FoldCV-Export-Attempt"), source = response.headers.get("X-FoldCV-Snapshot");
  if (!attemptId || source === null || expectedAttempt !== undefined && attemptId !== expectedAttempt) throw new Error("INVALID_RESULT");
  const snapshot: unknown = decodeJsonResponse(source);
  if (!snapshotShape(snapshot) || snapshotFields.some(key => snapshot[key] !== captured[key])) throw new Error("INVALID_RESULT");
  const blob = await boundedArtifact(response);
  const hash = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  const sha256 = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
  if (sha256 !== response.headers.get("X-FoldCV-Sha256")) throw new Error("ARTIFACT_BYTES_MISMATCH");
  return { blob, attemptId, snapshot };
}
