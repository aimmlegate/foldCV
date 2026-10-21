import { errorMessage } from "../errors/messages";
import type { GuiProjectResponse } from "../contracts/generated/gui_project_response";
import type { GuiCreateProjectRequest } from "../contracts/generated/gui_create_project_request";
import type { GuiStartGenerationRequest } from "../contracts/generated/gui_start_generation_request";
import type { SourceContextRequest } from "../contracts/generated/source_context_request";
import type { SourceContext } from "../contracts/generated/source_context";
import type { Mutation } from "../contracts/generated/mutation";
import type { MutationResult } from "../contracts/generated/mutation_result";
import type { GuiRewriteRequest } from "../contracts/generated/gui_rewrite_request";
import type { GuiAnalysisRequest } from "../contracts/generated/gui_analysis_request";
import type { SaveAnalysisPreference } from "../contracts/generated/save_analysis_preference";
import type { GuiProjectListResponse } from "../contracts/generated/gui_project_list_response";
import type { GuiDeleteProjectRequest } from "../contracts/generated/gui_delete_project_request";
import type { GuiDeleteProjectResult } from "../contracts/generated/gui_delete_project_result";
import type { GuiRenameProjectRequest } from "../contracts/generated/gui_rename_project_request";
import type { GuiArchiveRequest } from "../contracts/generated/gui_archive_request";
import type { RulesSettings } from "../contracts/generated/rules_settings";
import type { SaveRulesRequest } from "../contracts/generated/save_rules_request";
import type { GuiExportRequest } from "../contracts/generated/gui_export_request";
import type { Preferences } from "../contracts/generated/preferences";
import type { SaveImportModelPreference } from "../contracts/generated/save_import_model_preference";
import { validateContract } from "../contracts/validate";

export type Workspace = GuiProjectResponse["workspace"];
export class ApiFailure extends Error {
  constructor(readonly code: string, readonly recoveryProjectId: string | null = null) { super(code); }
}
function isResponse(value: unknown): value is GuiProjectResponse {
  return validateContract("gui_project_response", value);
}
function errorCode(value: unknown): string {
  if (typeof value !== "object" || value === null || !("error" in value)) return "REQUEST_FAILED";
  const error = value.error;
  return typeof error === "object" && error !== null && "code" in error && typeof error.code === "string"
    ? error.code : "REQUEST_FAILED";
}
async function request(path: string, method = "GET", body?: GuiCreateProjectRequest | GuiStartGenerationRequest | SourceContextRequest | GuiRewriteRequest | GuiExportRequest | GuiAnalysisRequest | SaveAnalysisPreference | SaveImportModelPreference | { model: string | null; effort: Preferences["rewriteReasoningEffort"] } | GuiDeleteProjectRequest | GuiRenameProjectRequest | SaveRulesRequest | Mutation | Record<string, never> | FormData): Promise<unknown> {
  const init: RequestInit = { method, credentials: "same-origin", cache: "no-store" };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "Content-Type": "application/json" }; }
  const response = await fetch(path, init);
  const value: unknown = await response.json();
  if (!response.ok) {
    const id = response.headers.get("X-FoldCV-Project-Id");
    throw new ApiFailure(errorCode(value), id !== null && /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(id) ? id : null);
  }
  return value;
}
export async function projectRequest(path: string, method = "GET", body?: GuiCreateProjectRequest | GuiStartGenerationRequest | GuiExportRequest | GuiAnalysisRequest | Record<string, never> | FormData): Promise<GuiProjectResponse> {
  const value = await request(path, method, body);
  if (!isResponse(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
function isContext(value: unknown): value is SourceContext { return validateContract("source_context", value); }
export async function sourceRequest(body: SourceContextRequest): Promise<SourceContext> {
  const value = await request(`/v1/projects/${body.projectId}/source-context`, "POST", body);
  if (!isContext(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
export async function migrationRequest(id: string): Promise<SourceContext> {
  const value = await request(`/v1/projects/${id}/migration-context`);
  if (!isContext(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
function isMutationResult(value: unknown): value is MutationResult { return validateContract("mutation_result", value); }
export async function mutationRequest(body: Mutation): Promise<MutationResult> {
  const value = await request(`/v1/projects/${body.projectId}/mutations`, "POST", body);
  if (!isMutationResult(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
export async function rewriteRequest(body: GuiRewriteRequest): Promise<MutationResult> {
  const value = await request(`/v1/projects/${body.selection.projectId}/rewrite`, "POST", body);
  if (!isMutationResult(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
function isRules(value: unknown): value is RulesSettings { return validateContract("rules_settings", value); }
export async function rulesRequest(): Promise<RulesSettings> {
  const value = await request("/v1/settings/rules");
  if (!isRules(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
export async function saveRulesRequest(body: SaveRulesRequest): Promise<RulesSettings> {
  const value = await request("/v1/settings/rules", "PUT", body);
  if (!isRules(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
function isPreferences(value: unknown): value is Preferences { return validateContract("preferences", value); }
export async function saveRewriteReasoningRequest(model: string | null, effort: Preferences["rewriteReasoningEffort"]): Promise<Preferences> {
  const value = await request("/v1/settings/rewrite-reasoning", "PUT", { model, effort: effort ?? null });
  if (!isPreferences(value)) throw new Error("Invalid preferences response");
  return value;
}
export async function saveImportModelRequest(model: string | null): Promise<Preferences> {
  const value = await request("/v1/settings/import-model", "PUT", { model });
  if (!isPreferences(value)) throw new Error("Invalid preferences response");
  return value;
}
export async function preferencesRequest(automaticAnalysis?: boolean): Promise<Preferences> {
  const value = automaticAnalysis === undefined ? await request("/v1/settings/preferences")
    : await request("/v1/settings/preferences", "PUT", { automaticAnalysis });
  if (!isPreferences(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
export async function analysisRequest(projectId: string, action: "invalidate" | "retry", fieldIds: string[] = []): Promise<GuiProjectResponse> {
  return projectRequest(`/v1/projects/${projectId}/analysis`, "POST", { action, fieldIds });
}
function isProjectList(value: unknown): value is GuiProjectListResponse { return validateContract("gui_project_list_response", value); }
function isDeleteResult(value: unknown): value is GuiDeleteProjectResult { return validateContract("gui_delete_project_result", value); }
export async function projectListRequest(): Promise<GuiProjectListResponse> {
  const value = await request("/v1/projects");
  if (!isProjectList(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
export async function renameProjectRequest(id: string, body: GuiRenameProjectRequest): Promise<GuiProjectResponse> {
  const value = await request(`/v1/projects/${id}/metadata`, "PATCH", body);
  if (!isResponse(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
export async function deleteProjectRequest(id: string): Promise<GuiDeleteProjectResult> {
  const value = await request(`/v1/projects/${id}`, "DELETE", { confirmed: true });
  if (!isDeleteResult(value)) throw new ApiFailure("INVALID_RESULT");
  return value;
}
export async function openArchiveRequest(file: File): Promise<GuiProjectResponse> {
  if (file.size > 64 * 1024 * 1024) throw new ApiFailure("ARCHIVE_SIZE_LIMIT");
  const body = new FormData();body.append("file", file);
  return projectRequest("/v1/projects/archive", "POST", body);
}
export async function archiveDownload(id: string, body: GuiArchiveRequest): Promise<Blob> {
  const response = await fetch(`/v1/projects/${id}/archive`, { method: "POST", credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) { const value: unknown = await response.json();throw new ApiFailure(errorCode(value)); }
  const blob = await response.blob();
  if (blob.type !== "application/vnd.foldcv.project+zip" || blob.size > 64 * 1024 * 1024 || blob.size < 22) throw new ApiFailure("INVALID_RESULT");
  return blob;
}
export async function docxDownload(path: string, expected: { sha256: string; size: number }): Promise<Blob> {
  // Workspace v5 keeps its old bound. The rich GUI uses rich/api.ts and 32 MiB.
  const response = await fetch(path, { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) { const raw: unknown = await response.json();throw new ApiFailure(errorCode(raw)); }
  if (!response.headers.get("Content-Type")?.startsWith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")) throw new ApiFailure("INVALID_RESULT");
  const blob = await response.blob();
  if (blob.size !== expected.size || blob.size > 8 * 1024 * 1024) throw new ApiFailure("INVALID_RESULT");
  const bytes = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  const sha256 = [...new Uint8Array(bytes)].map(byte => byte.toString(16).padStart(2, "0")).join("");
  if (sha256 !== expected.sha256) throw new ApiFailure("INVALID_RESULT");
  return blob;
}
export async function exchangeSession(): Promise<void> {
  const secret = new URLSearchParams(location.hash.slice(1)).get("secret");
  if (secret === null) return;
  history.replaceState(null, "", location.pathname + location.search);
  const response = await fetch("/v1/session/exchange", { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ secret }) });
  if (!response.ok) throw new ApiFailure("AUTH_REQUIRED");
}
export function errorLabel(error: unknown): string { return errorMessage(error); }
