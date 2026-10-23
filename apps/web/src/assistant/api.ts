import type { AssistantContinuationOptionsV1 } from "../contracts/generated/assistant_continuation_options_v1";
import type { AssistantRunOutcomeV1 } from "../contracts/generated/assistant_run_outcome_v1";
import type { AssistantContinueRunV1 } from "../contracts/generated/assistant_continue_run_v1";
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
import type { PreparedApi, PreparedActionApi } from "./editor-bridge";
import type { AssistantTaskCatalogV1 } from "../contracts/generated/assistant_task_catalog_v1";
import type { AssistantTaskCheckV1 } from "../contracts/generated/assistant_task_check_v1";
import { knownErrorMessage } from "../errors/messages";
import type { AssistantProposalV1 } from "../contracts/generated/assistant_proposal_v1";
import type { AssistantCapabilityReviewsV1 } from "../contracts/generated/assistant_capability_reviews_v1";
import type { AssistantCapabilityReviewV1 } from "../contracts/generated/assistant_capability_review_v1";
import type { AssistantProjectActionClaimV1 } from "../contracts/generated/assistant_project_action_claim_v1";
import type { AssistantProjectActionResultV1 } from "../contracts/generated/assistant_project_action_result_v1";
import type { AssistantHistoryOfferV1 } from "../contracts/generated/assistant_history_offer_v1";
import type { AssistantProposalRequestV1 } from "../contracts/generated/assistant_proposal_request_v1";
import type { AssistantAcceptanceV1 } from "../contracts/generated/assistant_acceptance_v1";
import type { AssistantApplicationClaimV1 } from "../contracts/generated/assistant_application_claim_v1";
import type { AssistantApplicationRecoveryV1 } from "../contracts/generated/assistant_application_recovery_v1";

type MessagePage = Omit<AgentMessagePage, "items"> & { items: AgentMessage[] };
type Replies = { assistant_continuation_options_v1: AssistantContinuationOptionsV1; assistant_run_outcome_v1: AssistantRunOutcomeV1; agent_project_operations: AgentProjectOperations; agent_access: AgentAccess; agent_capabilities: AgentCapabilities; agent_settings: AgentSettings; agent_conversation: AgentConversation;
  assistant_task_catalog_v1: AssistantTaskCatalogV1; assistant_task_check_v1: AssistantTaskCheckV1;
  assistant_proposal_v1: AssistantProposalV1; assistant_capability_reviews_v1: AssistantCapabilityReviewsV1; assistant_capability_review_v1: AssistantCapabilityReviewV1;
  assistant_project_action_claim_v1: AssistantProjectActionClaimV1; assistant_project_action_result_v1: AssistantProjectActionResultV1;
  assistant_application_claim_v1: AssistantApplicationClaimV1; assistant_application_recovery_v1: AssistantApplicationRecoveryV1;
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
  offerReviewedHistory(value: AssistantHistoryOfferV1): Promise<Record<string, never>> {
    return this.request("agent_empty_request", this.prefix + "/history/offer-v1", "POST", value,
      { "X-FoldCV-Assistant-Protocol": "1" });
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
  proposals(): Promise<AssistantCapabilityReviewsV1> {
    return this.request("assistant_capability_reviews_v1", this.prefix + "/reviews", "GET", {}, { "X-FoldCV-Assistant-Protocol": "1" });
  }
  continuations(flags: AgentFlags): Promise<AssistantContinuationOptionsV1> {
    return this.request("assistant_continuation_options_v1", this.prefix + "/continuations", "GET", {}, {
      "X-FoldCV-Assistant-Protocol": "1", "X-FoldCV-Agent-Edits": flags.allowEdits ? "1" : "0", "X-FoldCV-Agent-Web": flags.allowWeb ? "1" : "0" });
  }
  continueRun(value: AssistantContinueRunV1): Promise<AgentRun> {
    return this.request("agent_run", this.prefix + "/continuations/run", "POST", value, { "X-FoldCV-Assistant-Protocol": "1" });
  }
  outcome(runId: string): Promise<AssistantRunOutcomeV1> {
    return this.request("assistant_run_outcome_v1", this.prefix + `/outcomes/${encodeURIComponent(runId)}`, "GET", {}, { "X-FoldCV-Assistant-Protocol": "1" });
  }
  proposal(value: AssistantProposalRequestV1): Promise<AssistantCapabilityReviewV1> {
    return this.request("assistant_capability_review_v1", `${this.prefix}/reviews/${encodeURIComponent(value.proposalId)}/versions/${String(value.version)}`,
      "GET", {}, { "X-FoldCV-Assistant-Protocol": "1" });
  }
  discardProposal(value: AssistantProposalRequestV1): Promise<AssistantProposalV1> {
    return this.request("assistant_proposal_v1", this.prefix + "/proposals/discard", "POST", value, { "X-FoldCV-Assistant-Protocol": "1" });
  }
  cancelApplication(value: AssistantAcceptanceV1): Promise<AssistantApplicationRecoveryV1> {
    return this.request("assistant_application_recovery_v1", this.prefix + "/applications/cancel", "POST", value,
      { "X-FoldCV-Assistant-Protocol": "1" });
  }
  retryApplication(value: AssistantAcceptanceV1): Promise<AssistantProposalV1> {
    return this.request("assistant_proposal_v1", this.prefix + "/applications/retry", "POST", value,
      { "X-FoldCV-Assistant-Protocol": "1" });
  }
  reviewed(value: AssistantAcceptanceV1): PreparedApi {
    const accepted = structuredClone(value), headers = { "X-FoldCV-Assistant-Protocol": "1" };
    let claim: AgentClaimResult | null = null;
    return { resolve: async () => {
      let reply: AssistantApplicationClaimV1;
      try { reply = await this.request("assistant_application_claim_v1", this.prefix + "/applications/claim", "POST", accepted, headers); }
      catch (error) {
        if (error instanceof AgentApiFailure && error.status !== 0) throw error;
        const recovered = await this.request("assistant_application_recovery_v1", this.prefix + "/applications/resume", "POST", accepted, headers);
        if (!recovered.claim) throw new AgentApiFailure(recovered.result?.receipt.durable ? "AGENT_OUTCOME_UNKNOWN" : "AGENT_SAVE_FAILED");
        reply = recovered.claim;
      }
      if (reply.accepted.proposalId !== accepted.proposalId || reply.accepted.version !== accepted.version
        || reply.accepted.contentSha256 !== accepted.contentSha256 || reply.accepted.acceptanceId !== accepted.acceptanceId)
        throw new AgentApiFailure("AGENT_IDEMPOTENCY_CONFLICT");
      claim = reply.claim; return claim.batch.id;
    }, claim: id => claim?.batch.id === id ? Promise.resolve(claim) : Promise.reject(new AgentApiFailure("AGENT_PROTOCOL")),
    commit: (current, writer) => this.request("agent_commit_result", this.prefix + "/applications/commit", "POST",
      { ...accepted, ticket: current.ticket, requestSha256: current.batch.requestSha256, writer: writer ?? null }, headers),
    recover: async () => {
      const value = await this.request("assistant_application_recovery_v1", this.prefix + "/applications/recover", "POST", accepted, headers);
      if (value.reloadRequired && value.savedReceipt) return { receipt: value.savedReceipt, project: null };
      return value.result ?? (value.savedReceipt ? { receipt: value.savedReceipt, project: null } : null);
    },
    report: async receipt => { await this.request("assistant_proposal_v1", this.prefix + "/applications/result", "POST", { ...accepted, receipt }, headers); } };
  }
  cancelAction(value: AssistantAcceptanceV1): Promise<AssistantProjectActionResultV1> {
    return this.request("assistant_project_action_result_v1", this.prefix + "/actions/cancel", "POST", value,
      { "X-FoldCV-Assistant-Protocol": "1" });
  }
  retryAction(value: AssistantAcceptanceV1): Promise<AssistantProposalV1> {
    return this.request("assistant_proposal_v1", this.prefix + "/actions/retry", "POST", value,
      { "X-FoldCV-Assistant-Protocol": "1" });
  }
  reviewedAction(value: AssistantAcceptanceV1): PreparedActionApi {
    const accepted = structuredClone(value), headers = { "X-FoldCV-Assistant-Protocol": "1" };
    const checked = (reply: AssistantProjectActionResultV1): AssistantProjectActionResultV1 => {
      if (reply.proposal.id !== accepted.proposalId || reply.proposal.version !== accepted.version
        || reply.proposal.contentSha256 !== accepted.contentSha256 || reply.proposal.projectId !== this.projectId
        || reply.operation && (reply.operation.projectId !== this.projectId || reply.operation.runId !== reply.proposal.originRunId)
        || reply.project && reply.project.workspace.projectId !== this.projectId) throw new AgentApiFailure("AGENT_IDEMPOTENCY_CONFLICT");
      return reply;
    };
    return { claim: async () => {
      let reply: AssistantProjectActionClaimV1;
      try { reply = await this.request("assistant_project_action_claim_v1", this.prefix + "/actions/claim", "POST", accepted, headers); }
      catch (error) {
        if (error instanceof AgentApiFailure && error.status !== 0) throw error;
        const recovered = await this.request("assistant_project_action_result_v1", this.prefix + "/actions/resume", "POST", accepted, headers);
        if (!recovered.claim) throw new AgentApiFailure("AGENT_SAVE_FAILED");
        reply = recovered.claim;
      }
      if (reply.accepted.proposalId !== accepted.proposalId || reply.accepted.version !== accepted.version
        || reply.accepted.contentSha256 !== accepted.contentSha256 || reply.accepted.acceptanceId !== accepted.acceptanceId)
        throw new AgentApiFailure("AGENT_IDEMPOTENCY_CONFLICT");
      return reply;
    }, commit: async (claim, writer) => checked(await this.request("assistant_project_action_result_v1", this.prefix + "/actions/commit", "POST",
      { ...accepted, ticket: claim.ticket, requestSha256: claim.requestSha256, writer }, headers)),
    recover: async () => checked(await this.request("assistant_project_action_result_v1", this.prefix + "/actions/recover", "POST", accepted, headers)),
    cancel: async () => { await this.cancelAction(accepted); } };
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
  submit(request: AgentRunRequest, protocol = false): Promise<AgentRun> {
    return this.request("agent_run", `${this.prefix}/conversations/${encodeURIComponent(request.conversationId)}/${protocol ? "requests" : "runs"}`,
      "POST", protocol ? { protocolVersion: 1, request } : request, protocol ? { "X-FoldCV-Assistant-Protocol": "1" } : {});
  }
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
