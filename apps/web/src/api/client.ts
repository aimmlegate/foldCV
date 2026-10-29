import type { RulesSettings } from "../contracts/generated/rules_settings";
import type { SaveRulesRequest } from "../contracts/generated/save_rules_request";
import type { Preferences } from "../contracts/generated/preferences";
import type { SaveLimitsPreference } from "../contracts/generated/save_limits_preference";

/** The session exchange and the /v1/settings calls; replies are parsed with JSON.parse and typed (plan 2.6). */
export class ApiFailure extends Error {
  constructor(readonly code: string) { super(code); }
}
function errorCode(value: unknown): string {
  if (typeof value !== "object" || value === null || !("error" in value)) return "REQUEST_FAILED";
  const error = value.error;
  return typeof error === "object" && error !== null && "code" in error && typeof error.code === "string"
    ? error.code : "REQUEST_FAILED";
}
async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", cache: "no-store" };
  if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "Content-Type": "application/json" }; }
  const response = await fetch(path, init);
  const text = await response.text();
  let value: unknown = null;
  try { value = text ? JSON.parse(text) : null; } catch { throw new ApiFailure("INVALID_RESULT"); }
  if (!response.ok) throw new ApiFailure(errorCode(value));
  if (typeof value !== "object" || value === null) throw new ApiFailure("INVALID_RESULT");
  return value as T;
}
export function rulesRequest(): Promise<RulesSettings> { return request<RulesSettings>("/v1/settings/rules"); }
export function saveRulesRequest(body: SaveRulesRequest): Promise<RulesSettings> { return request<RulesSettings>("/v1/settings/rules", "PUT", body); }
export function saveRewriteReasoningRequest(model: string | null, effort: Preferences["rewriteReasoningEffort"]): Promise<Preferences> {
  return request<Preferences>("/v1/settings/rewrite-reasoning", "PUT", { model, effort: effort ?? null });
}
export function saveImportModelRequest(model: string | null): Promise<Preferences> {
  return request<Preferences>("/v1/settings/import-model", "PUT", { model });
}
export function saveFallbackModelRequest(model: string | null): Promise<Preferences> {
  return request<Preferences>("/v1/settings/fallback-model", "PUT", { model });
}
export function saveLimitsRequest(body: SaveLimitsPreference): Promise<Preferences> {
  return request<Preferences>("/v1/settings/limits", "PUT", body);
}
export function preferencesRequest(): Promise<Preferences> { return request<Preferences>("/v1/settings/preferences"); }
export async function exchangeSession(): Promise<void> {
  const secret = new URLSearchParams(location.hash.slice(1)).get("secret");
  if (secret === null) return;
  history.replaceState(null, "", location.pathname + location.search);
  const response = await fetch("/v1/session/exchange", { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ secret }) });
  if (!response.ok) throw new ApiFailure("AUTH_REQUIRED");
}
