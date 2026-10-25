import Ajv2020 from "ajv/dist/2020.js";
import { taggedSchema } from "../contracts/tagged-schema";
import { decodeJsonResponse } from "../contracts/json-response";
import { parseJsonWire, type JsonWireNode } from "../contracts/lossless-json";
import { templateProjectReply } from "../contracts/template-validate";
import type { TemplateProjectResponseV1 } from "../contracts/generated/template_project_response_v1";
import type { TemplateSnapshotIdentity } from "../contracts/generated/template_snapshot_identity";
import { templateExportArtifact } from "../contracts/template-export";
import schema from "../../../../contracts/json-schema/rich_project_response.schema.json" with { type: "json" };
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import type { ImageUploadCapture } from "../contracts/generated/image_upload_capture";
import type { ImageSessionRequest } from "../contracts/generated/image_session_request";
import imageSessionSchema from "../../../../contracts/json-schema/image_session_request.schema.json" with { type: "json" };
import { validateContract } from "../contracts/validate";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";
import type { GuiDeleteProjectResult } from "../contracts/generated/gui_delete_project_result";
import type { TimelineReport } from "../contracts/generated/timeline_report";
import type { DateCascadeProposal } from "../contracts/generated/date_cascade_proposal";
import type { CascadeRequest } from "../contracts/generated/cascade_request";
import timelineSchema from "../../../../contracts/json-schema/timeline_report.schema.json" with { type: "json" };
import cascadeSchema from "../../../../contracts/json-schema/date_cascade_proposal.schema.json" with { type: "json" };
import archiveSchema from "../../../../contracts/json-schema/archive_manifest_v7.schema.json" with { type: "json" };

const ajv = new Ajv2020({ strict: false, allErrors: true, discriminator: true });
const responseShape = ajv.compile<RichProjectResponse>(taggedSchema(schema));
const timelineShape = ajv.compile<TimelineReport>(taggedSchema(timelineSchema));
const cascadeShape = ajv.compile<DateCascadeProposal>(taggedSchema(cascadeSchema));
export const validateImageSession = ajv.compile<ImageSessionRequest>(imageSessionSchema);
const prefix = "/v1/rich/projects";
export class RichApiFailure extends Error {
  constructor(readonly code: string, readonly status = 0) { super(code); }
}
async function jsonRequest(path: string, init: RequestInit): Promise<unknown> {
  const response = await fetch(path, init);
  const value = decodeJsonResponse(await response.text());
  if (!response.ok) {
    const code = typeof value === "object" && value !== null && "error" in value && typeof value.error === "object"
      && value.error !== null && "code" in value.error && typeof value.error.code === "string" ? value.error.code : "REQUEST_FAILED";
    throw new RichApiFailure(code, response.status);
  }
  return value;
}
export function rootRequest(path: string, method = "GET", body?: unknown, headers: Record<string, string> = {}): Promise<unknown> {
  const init: RequestInit = { method, credentials: "same-origin", cache: "no-store", headers };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { ...headers, "Content-Type": "application/json" }; }
  return jsonRequest(path, init);
}
export function request(path: string, method = "GET", body?: unknown, headers?: Record<string, string>): Promise<unknown> { return rootRequest(prefix + path, method, body, headers); }
export function requestWire(path: string, body: JsonWireNode): Promise<unknown> {
  return jsonRequest(prefix + path, { method: "POST", credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json" }, body: parseJsonWire(body.wire).wire });
}
export type TemplateImportPackage = { id: string; name: string; revision: string; packageHash: string };
/** Strict template import is offered only when the service has it configured; it names the store's active package. */
export async function templateImportStatus(): Promise<TemplateImportPackage | null> {
  const value = await rootRequest("/v1/rich/template-import");
  if (typeof value !== "object" || value === null || Reflect.get(value, "schemaVersion") !== 1) throw new RichApiFailure("INVALID_RESULT");
  const available: unknown = Reflect.get(value, "available"), item: unknown = Reflect.get(value, "package");
  if (available !== true) return null;
  const text = (key: string) => { const field: unknown = typeof item === "object" && item !== null ? Reflect.get(item, key) : null;
    if (typeof field !== "string" || !field) throw new RichApiFailure("INVALID_RESULT"); return field; };
  return { id: text("id"), name: text("name"), revision: text("revision"), packageHash: text("packageHash") };
}
export async function projectRequest(path: string, method = "GET", body?: unknown): Promise<RichProjectResponse> {
  const response = await request(path, method, body);
  if (!responseShape(response)) throw new RichApiFailure("INVALID_RESULT");
  return response;
}
export type OpenedProject = { kind: "rich"; response: RichProjectResponse } | { kind: "template"; response: TemplateProjectResponseV1 };
/** One read decides the family: a V7 workspace answers with the verified template response. */
export async function openedProject(path: string, method = "GET", body?: unknown): Promise<OpenedProject> {
  const value = await request(path, method, body);
  const workspace = typeof value === "object" && value !== null && "workspace" in value ? value.workspace : null;
  if (typeof workspace === "object" && workspace !== null && "schemaVersion" in workspace && workspace.schemaVersion === 7) {
    const response = await templateProjectReply(value);
    if (!response) throw new RichApiFailure("INVALID_RESULT");
    return { kind: "template", response };
  }
  if (!responseShape(value)) throw new RichApiFailure("INVALID_RESULT");
  return { kind: "rich", response: value };
}
export async function templateProjectRequest(path: string, method = "GET", body?: unknown): Promise<TemplateProjectResponseV1> {
  const response = await templateProjectReply(await request(path, method, body));
  if (!response) throw new RichApiFailure("INVALID_RESULT");
  return response;
}
export async function listProjects(): Promise<GuiProjectListResponse> {
  const response = await request("");
  if (!isProjectList(response)) throw new RichApiFailure("INVALID_RESULT");
  return response;
}
function isProjectList(value: unknown): value is GuiProjectListResponse { return validateContract("gui_project_list_response", value); }
export async function deleteProject(id: string): Promise<GuiDeleteProjectResult> {
  const value = await request(`/${id}/delete`, "POST", { confirmed: true });
  if (!isDeleteResult(value)) throw new RichApiFailure("INVALID_RESULT");
  return value;
}
function isDeleteResult(value: unknown): value is GuiDeleteProjectResult { return validateContract("gui_delete_project_result", value); }
export async function readTimeline(id: string): Promise<TimelineReport> {
  const value = await request(`/${id}/timeline`);
  if (!timelineShape(value)) throw new RichApiFailure("INVALID_RESULT");
  return value;
}
export async function previewCascade(id: string, payload: CascadeRequest): Promise<DateCascadeProposal> {
  const value = await request(`/${id}/cascade`, "POST", payload);
  if (!cascadeShape(value)) throw new RichApiFailure("INVALID_RESULT");
  return value;
}
export function saveMutation(request: RichMutation): Promise<RichProjectResponse> {
  return projectRequest(`/${request.projectId}/mutations`, "POST", request);
}
export const imageSource = (project: string, asset: string): string => `${prefix}/${encodeURIComponent(project)}/images/${encodeURIComponent(asset)}`;
export async function uploadImage(project: string, file: File, capture: ImageUploadCapture, signal: AbortSignal) {
  const body = new FormData(); body.append("file", file);
  const headers: Record<string, string> = { "X-FoldCV-Session": capture.sessionId, "X-FoldCV-Revision": String(capture.revision),
    "X-FoldCV-Action": capture.actionId, "X-FoldCV-Reservation": capture.reservationId };
  if (capture.replacementId) headers["X-FoldCV-Replacement"] = capture.replacementId;
  const response = await fetch(`${prefix}/${encodeURIComponent(project)}/images/upload`, { method: "POST", body, headers, credentials: "same-origin", cache: "no-store", signal });
  const value: unknown = await response.json();
  if (!response.ok) {
    const code = typeof value === "object" && value !== null && "error" in value && typeof value.error === "object" && value.error !== null
      && "code" in value.error && typeof value.error.code === "string" ? value.error.code : "IMAGE_IMPORT_FAILED";
    throw new RichApiFailure(code, response.status);
  }
  if (!responseShape(value)) throw new RichApiFailure("INVALID_RESULT");
  const asset = value.workspace.project?.assets.find(asset => asset.id === response.headers.get("X-FoldCV-Asset"));
  if (!asset) throw new RichApiFailure("INVALID_RESULT");
  return { asset, response: value };
}
export async function download(id: string, kind: "export" | "archive", revision: { projectRevision: number; documentRevision: number }): Promise<Blob> {
  const response = await fetch(`${prefix}/${id}/${kind}`, { method: "POST", credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(kind === "archive"
      ? { projectRevision: revision.projectRevision, documentRevision: revision.documentRevision } : {}) });
  if (!response.ok) {
    const value: unknown = await response.json();
    const code = typeof value === "object" && value !== null && "error" in value && typeof value.error === "object"
      && value.error !== null && "code" in value.error && typeof value.error.code === "string" ? value.error.code : "EXPORT_FAILED";
    throw new RichApiFailure(code, response.status);
  }
  const blob = await response.blob();
  const maximum = kind === "export" ? 32 * 1024 * 1024 : archiveSchema["x-maxArchiveBytes"];
  const mime = kind === "export" ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document" : "application/vnd.foldcv.project+zip";
  if (!blob.size || blob.size > maximum || blob.type !== mime) throw new RichApiFailure("INVALID_RESULT");
  if (kind === "export") {
    const hash = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
    const sha256 = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
    if (sha256 !== response.headers.get("X-FoldCV-Sha256")) throw new RichApiFailure("ARTIFACT_BYTES_MISMATCH");
  }
  return blob;
}

export async function downloadTemplate(id: string, snapshot: TemplateSnapshotIdentity, options: { retryAttemptId?: string; signal?: AbortSignal } = {}) {
  const captured = structuredClone(snapshot);
  if (id !== captured.projectId) throw new RichApiFailure("INVALID_RESULT");
  const path = options.retryAttemptId === undefined ? `/${encodeURIComponent(id)}/export`
    : `/${encodeURIComponent(id)}/exports/${encodeURIComponent(options.retryAttemptId)}/retry`;
  const init: RequestInit = { method: "POST", credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(options.retryAttemptId === undefined ? { schemaVersion: 1, snapshot: captured } : {}) };
  if (options.signal !== undefined) init.signal = options.signal;
  const response = await fetch(prefix + path, init);
  if (!response.ok) {
    const value = decodeJsonResponse(await response.text());
    const code = typeof value === "object" && value !== null && "error" in value && typeof value.error === "object"
      && value.error !== null && "code" in value.error && typeof value.error.code === "string" ? value.error.code : "EXPORT_FAILED";
    throw new RichApiFailure(code, response.status);
  }
  try { return await templateExportArtifact(response, captured); }
  catch (error) { throw new RichApiFailure(error instanceof Error && error.message === "ARTIFACT_BYTES_MISMATCH" ? error.message : "INVALID_RESULT"); }
}
