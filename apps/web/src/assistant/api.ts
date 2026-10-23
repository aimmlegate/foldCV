import type { AgentCapabilities } from "../contracts/generated/agent_capabilities";
import type { AgentAccess } from "../contracts/generated/agent_access";
import type { AgentHistoryOffer } from "../contracts/generated/agent_history_offer";
import type { AgentProjectOperations } from "../contracts/generated/agent_project_operations";
import type { AgentSettings } from "../contracts/generated/agent_settings";
import type { AgentSettingsRequest } from "../contracts/generated/agent_settings_request";
import type { AgentConversation } from "../contracts/generated/agent_conversation";
import type { AgentConversationPage } from "../contracts/generated/agent_conversation_page";
import type { AgentMessagePage } from "../contracts/generated/agent_message_page";
import type { AgentMessage } from "../contracts/generated/agent_message";
import type { AgentResourcePage } from "../contracts/generated/agent_resource_page";
import type { AgentLease } from "../contracts/generated/agent_lease";
import type { AgentRun } from "../contracts/generated/agent_run";
import type { AgentRunRequest } from "../contracts/generated/agent_run_request";
import type { AgentRunRead } from "../contracts/generated/agent_run_read";
import type { AgentEvent } from "../contracts/generated/agent_event";
import type { AgentClaimResult } from "../contracts/generated/agent_claim_result";
import type { AgentCommitResult } from "../contracts/generated/agent_commit_result";
import type { AgentEditReceipt } from "../contracts/generated/agent_edit_receipt";
import type { AgentOwnerRequest } from "../contracts/generated/agent_owner_request";
import type { AgentPageRequest } from "../contracts/generated/agent_page_request";
import type { RichProjectResponse } from "../contracts/generated/rich_project_response";
import { validateContract } from "../contracts/validate";
import type { PreparedApi } from "./editor-bridge";
import type { AssistantTaskCatalogV1 } from "../contracts/generated/assistant_task_catalog_v1";
import type { AssistantTaskCheckV1 } from "../contracts/generated/assistant_task_check_v1";
import { knownErrorMessage } from "../errors/messages";

type MessagePage = Omit<AgentMessagePage, "items"> & { items: AgentMessage[] };
type Replies = { agent_project_operations: AgentProjectOperations; agent_access: AgentAccess; agent_capabilities: AgentCapabilities; agent_settings: AgentSettings; agent_conversation: AgentConversation;
  assistant_task_catalog_v1: AssistantTaskCatalogV1; assistant_task_check_v1: AssistantTaskCheckV1;
  agent_conversation_page: AgentConversationPage; agent_message_page: MessagePage; agent_resource_page: AgentResourcePage;
  agent_lease: AgentLease; agent_run: AgentRun; agent_run_read: AgentRunRead; agent_claim_result: AgentClaimResult;
  agent_commit_result: AgentCommitResult; agent_edit_receipt: AgentEditReceipt; agent_empty_request: Record<string, never>;
  rich_project_response: RichProjectResponse };
export type AgentOwner = AgentOwnerRequest["owner"];
export type AgentFlags = { allowEdits: boolean; allowWeb: boolean };
export class AgentApiFailure extends Error {
  constructor(readonly code: string, readonly status = 0) { super(code); }
}
function object(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function shape<K extends keyof Replies>(kind: K, value: unknown): value is Replies[K] {
  if (!validateContract(kind, value)) return false;
  // The type generator loses nested fields when a schema has conditional allOf.
  return kind !== "agent_message_page" || object(value) && Array.isArray(value.items)
    && value.items.every((item: unknown) => validateContract("agent_message", item));
}
function eventShape(value: unknown): value is AgentEvent { return validateContract("agent_event", value); }
async function successful(response: Response): Promise<Response> {
  if (response.ok) return response;
  let value: unknown;
  try { value = await response.json(); } catch { throw new AgentApiFailure("REQUEST_FAILED", response.status); }
  const supplied = object(value) && object(value.error) && typeof value.error.code === "string" ? value.error.code : "REQUEST_FAILED";
  const code = validateContract("agent_error", { code: supplied }) || knownErrorMessage(supplied) !== null || ["AUTH_REQUIRED", "ORIGIN_DENIED", "HOST_DENIED", "INVALID_REQUEST", "INPUT_TOO_LARGE", "REQUEST_TIMEOUT", "INTERNAL_ERROR", "NOT_FOUND", "METHOD_NOT_ALLOWED"].includes(supplied) ? supplied : "REQUEST_FAILED";
  throw new AgentApiFailure(code, response.status);
}
function pageShape(value: unknown): value is AgentPageRequest { return validateContract("agent_page_request", value); }
function page(cursor: string | null = null, ids: string[] = []): AgentPageRequest {
  const value = { cursor, limit: 20, ids };
  if (!pageShape(value)) throw new AgentApiFailure("INVALID_REQUEST");
  return value;
}

export class AgentBrowserApi {
  readonly prefix: string;
  constructor(readonly projectId: string, private readonly transport: typeof fetch = (input, init) => fetch(input, init)) {
    this.prefix = `/v1/rich/projects/${encodeURIComponent(projectId)}/assistant`;
  }
  private async request<K extends keyof Replies>(kind: K, path: string, method = "POST", body: unknown = {}, headers: Record<string, string> = {}, keepalive = false): Promise<Replies[K]> {
    const response = await successful(await this.transport(path, { method, credentials: "same-origin", cache: "no-store",
      ...(keepalive ? { keepalive: true } : {}),
      headers: method === "GET" ? headers : { ...headers, "Content-Type": "application/json" }, ...(method === "GET" ? {} : { body: JSON.stringify(body) }) }));
    const value: unknown = await response.json();
    if (!shape(kind, value)) throw new AgentApiFailure("INVALID_RESULT");
    return value;
  }
  settings(): Promise<AgentSettings> { return this.request("agent_settings", "/v1/settings/assistant", "GET"); }
  access(): Promise<AgentAccess> { return this.request("agent_access", this.prefix + "/access", "GET"); }
  operations(): Promise<AgentProjectOperations> { return this.request("agent_project_operations", this.prefix + "/operations", "GET"); }
  offerHistory(value: AgentHistoryOffer): Promise<Record<string, never>> {
    return this.request("agent_empty_request", this.prefix + "/history/offer", "POST", value);
  }
  setAccess(expectedRevision: number, readOnly: boolean): Promise<AgentAccess> {
    return this.request("agent_access", this.prefix + "/access", "PUT", { expectedRevision, readOnly });
  }
  saveSettings(value: AgentSettingsRequest): Promise<AgentSettings> { return this.request("agent_settings", "/v1/settings/assistant", "PUT", value); }
  capabilities(flags: AgentFlags): Promise<AgentCapabilities> {
    return this.request("agent_capabilities", this.prefix + "/capabilities", "GET", {}, {
      "X-FoldCV-Agent-Edits": flags.allowEdits ? "1" : "0", "X-FoldCV-Agent-Web": flags.allowWeb ? "1" : "0" });
  }
  tasks(flags: AgentFlags): Promise<AssistantTaskCatalogV1> {
    return this.request("assistant_task_catalog_v1", this.prefix + "/tasks", "GET", {}, {
      "X-FoldCV-Assistant-Protocol": "1", "X-FoldCV-Agent-Edits": flags.allowEdits ? "1" : "0",
      "X-FoldCV-Agent-Web": flags.allowWeb ? "1" : "0" });
  }
  checkMessage(message: string, flags: AgentFlags): Promise<AssistantTaskCheckV1> {
    return this.request("assistant_task_check_v1", this.prefix + "/tasks/check-message", "POST",
      { schemaVersion: 1, protocolVersion: 1, message, scope: "resume", ...flags }, { "X-FoldCV-Assistant-Protocol": "1" });
  }
  conversations(cursor: string | null = null): Promise<AgentConversationPage> { return this.request("agent_conversation_page", this.prefix + "/conversations/read", "POST", page(cursor)); }
  conversation(): Promise<AgentConversation> { return this.request("agent_conversation", this.prefix + "/conversations"); }
  messages(id: string, cursor: string | null = null): Promise<MessagePage> { return this.request("agent_message_page", `${this.prefix}/conversations/${encodeURIComponent(id)}/read`, "POST", page(cursor)); }
  resources(id: string, kind: "sources" | "findings", ids: string[], cursor: string | null = null): Promise<AgentResourcePage> {
    return this.request("agent_resource_page", `${this.prefix}/conversations/${encodeURIComponent(id)}/${kind}/read`, "POST", page(cursor, ids));
  }
  open(sessionId: string): Promise<AgentLease> { return this.request("agent_lease", this.prefix + "/lease/open", "POST", { sessionId }); }
  renew(owner: AgentOwner): Promise<AgentLease> { return this.request("agent_lease", this.prefix + "/lease/renew", "POST", { owner }); }
  close(owner: AgentOwner): Promise<Record<string, never>> { return this.request("agent_empty_request", this.prefix + "/lease/close", "POST", { owner }, {}, true); }
  submit(request: AgentRunRequest): Promise<AgentRun> { return this.request("agent_run", `${this.prefix}/conversations/${encodeURIComponent(request.conversationId)}/runs`, "POST", request); }
  read(runId: string): Promise<AgentRunRead> { return this.request("agent_run_read", `${this.prefix}/runs/${encodeURIComponent(runId)}/read`); }
  cancel(runId: string, owner: AgentOwner): Promise<AgentRun> { return this.request("agent_run", `${this.prefix}/runs/${encodeURIComponent(runId)}/cancel`, "POST", { owner }); }
  claim(runId: string, batchId: string, owner: AgentOwner): Promise<AgentClaimResult> {
    return this.request("agent_claim_result", `${this.prefix}/runs/${encodeURIComponent(runId)}/edits/${encodeURIComponent(batchId)}/claim`, "POST", { owner });
  }
  prepared(runId: string, owner: AgentOwner): PreparedApi {
    return { claim: batchId => this.claim(runId, batchId, owner),
      commit: claim => this.request("agent_commit_result", `${this.prefix}/runs/${encodeURIComponent(runId)}/edits/${encodeURIComponent(claim.batch.id)}/commit`, "POST",
        { owner, ticket: claim.ticket, requestSha256: claim.batch.requestSha256 }),
      recover: async batchId => {
        const result = await this.read(runId), receipt = result.receipts.find(item => item.batchId === batchId);
        if (!receipt) return null;
        const project = await this.request("rich_project_response", `/v1/rich/projects/${encodeURIComponent(this.projectId)}`, "GET");
        const value = { receipt, project };
        if (!shape("agent_commit_result", value)) throw new AgentApiFailure("INVALID_RESULT");
        return value;
      }, report: async receipt => { await this.report(runId, owner, receipt); } };
  }
  report(runId: string, owner: AgentOwner, receipt: AgentEditReceipt): Promise<AgentEditReceipt> {
    return this.request("agent_edit_receipt", `${this.prefix}/runs/${encodeURIComponent(runId)}/edits/${encodeURIComponent(receipt.batchId)}/result`, "POST", { owner, receipt });
  }
  async *events(runId: string, owner: AgentOwner, afterSequence: number, signal: AbortSignal): AsyncGenerator<AgentEvent> {
    const response = await successful(await this.transport(`${this.prefix}/runs/${encodeURIComponent(runId)}/events`, { method: "POST",
      credentials: "same-origin", cache: "no-store", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner, afterSequence }), signal }));
    if (!response.body || !response.headers.get("content-type")?.startsWith("application/x-ndjson")) throw new AgentApiFailure("INVALID_RESULT");
    const reader = response.body.getReader(), decoder = new TextDecoder("utf-8", { fatal: true });
    let buffer = "", received = 0;
    try {
      while (true) {
        const next = await reader.read();
        if (next.done) break;
        received += next.value.byteLength;
        if (received > 256 * 1024) throw new AgentApiFailure("AGENT_OUTPUT_LIMIT");
        buffer += decoder.decode(next.value, { stream: true });
        let index: number;
        while ((index = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, index); buffer = buffer.slice(index + 1);
          if (!line.trim()) continue;
          if (new TextEncoder().encode(line).length > 65536) throw new AgentApiFailure("AGENT_OUTPUT_LIMIT");
          let value: unknown;
          try { value = JSON.parse(line); } catch { throw new AgentApiFailure("INVALID_RESULT"); }
          if (!eventShape(value)) throw new AgentApiFailure("INVALID_RESULT");
          yield value;
        }
        if (new TextEncoder().encode(buffer).length > 65536) throw new AgentApiFailure("AGENT_OUTPUT_LIMIT");
      }
      buffer += decoder.decode();
      if (buffer.trim()) throw new AgentApiFailure("INVALID_RESULT");
    } finally {
      await reader.cancel().catch(() => {}); reader.releaseLock();
    }
  }
}
