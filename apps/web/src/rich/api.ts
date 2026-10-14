import Ajv2020 from "ajv/dist/2020.js";
import schema from "../../../../contracts/json-schema/rich_project_response.schema.json" with { type: "json" };
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import type { RichMutation } from "../contracts/generated/rich_mutation";
import { validateContract } from "../contracts/validate";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";

const ajv = new Ajv2020({ strict: false, allErrors: true });
const responseShape = ajv.compile<RichProjectResponse>(schema);
const prefix = "/v1/rich/projects";
export class RichApiFailure extends Error {
  constructor(readonly code: string, readonly status = 0) { super(code); }
}
export async function request(path: string, method = "GET", body?: unknown): Promise<unknown> {
  const init: RequestInit = { method, credentials: "same-origin", cache: "no-store" };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "Content-Type": "application/json" }; }
  const response = await fetch(prefix + path, init);
  const value: unknown = await response.json();
  if (!response.ok) {
    const code = typeof value === "object" && value !== null && "error" in value && typeof value.error === "object"
      && value.error !== null && "code" in value.error && typeof value.error.code === "string" ? value.error.code : "REQUEST_FAILED";
    throw new RichApiFailure(code, response.status);
  }
  return value;
}
export async function projectRequest(path: string, method = "GET", body?: unknown): Promise<RichProjectResponse> {
  const response = await request(path, method, body);
  if (!responseShape(response)) throw new RichApiFailure("INVALID_RESULT");
  return response;
}
export async function listProjects(): Promise<GuiProjectListResponse> {
  const response = await request("");
  if (!isProjectList(response)) throw new RichApiFailure("INVALID_RESULT");
  return response;
}
function isProjectList(value: unknown): value is GuiProjectListResponse { return validateContract("gui_project_list_response", value); }
export function saveMutation(request: RichMutation): Promise<RichProjectResponse> {
  return projectRequest(`/${request.projectId}/mutations`, "POST", request);
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
  const maximum = (kind === "export" ? 32 : 64) * 1024 * 1024;
  const mime = kind === "export" ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document" : "application/vnd.foldcv.project+zip";
  if (!blob.size || blob.size > maximum || blob.type !== mime) throw new RichApiFailure("INVALID_RESULT");
  if (kind === "export") {
    const hash = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
    const sha256 = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
    if (sha256 !== response.headers.get("X-FoldCV-Sha256")) throw new RichApiFailure("ARTIFACT_BYTES_MISMATCH");
  }
  return blob;
}
