import type { GuiProjectResponse } from "../contracts/generated/gui_project_response";
import type { GuiCreateProjectRequest } from "../contracts/generated/gui_create_project_request";
import type { GuiStartGenerationRequest } from "../contracts/generated/gui_start_generation_request";
import type { SourceContextRequest } from "../contracts/generated/source_context_request";
import type { SourceContext } from "../contracts/generated/source_context";
import type { Mutation } from "../contracts/generated/mutation";
import type { MutationResult } from "../contracts/generated/mutation_result";
import type { GuiRewriteRequest } from "../contracts/generated/gui_rewrite_request";
import type { RulesSettings } from "../contracts/generated/rules_settings";
import type { GuiExportRequest } from "../contracts/generated/gui_export_request";
import { validateContract } from "../contracts/validate";

export type Workspace = GuiProjectResponse["workspace"];
export class ApiFailure extends Error {
  constructor(readonly code: string) { super(code); }
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
async function request(path: string, method = "GET", body?: GuiCreateProjectRequest | GuiStartGenerationRequest | SourceContextRequest | GuiRewriteRequest | GuiExportRequest | Mutation | Record<string, never> | FormData): Promise<unknown> {
  const init: RequestInit = { method, credentials: "same-origin", cache: "no-store" };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "Content-Type": "application/json" }; }
  const response = await fetch(path, init);
  const value: unknown = await response.json();
  if (!response.ok) throw new ApiFailure(errorCode(value));
  return value;
}
export async function projectRequest(path: string, method = "GET", body?: GuiCreateProjectRequest | GuiStartGenerationRequest | GuiExportRequest | Record<string, never> | FormData): Promise<GuiProjectResponse> {
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
export async function docxDownload(path: string, expected: { sha256: string; size: number }): Promise<Blob> {
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
export function errorLabel(error: unknown): string {
  const code = error instanceof ApiFailure ? error.code : "REQUEST_FAILED";
  const labels: Record<string, string> = { CONNECTION_REQUIRED: "Подключите модель перед созданием резюме.",
    AUTH_REQUIRED: "Откройте приложение по ссылке из запуска.", NO_USABLE_TEXT: "Доступного текста нет. Выберите другой файл или вставьте текст.",
    INPUT_TOO_LARGE: "Текст слишком большой для одного запроса.", CANCELLED: "Создание отменено. Исходник сохранён в памяти.",
    MODEL_DENIED: "Выбранная модель недоступна.", QUOTA_EXHAUSTED: "Лимит модели исчерпан. Повторите позже." };
  return labels[code] ?? "Не удалось завершить действие. Исходник и выполненные шаги доступны для повтора.";
}
