import type { AgentSettings } from "../contracts/generated/contracts";
import type { AgentSettingsRequest } from "../contracts/generated/contracts";
import type { AssistantCapabilitiesV1 } from "../contracts/generated/contracts";
import type { AssistantChangeProposalListV1 } from "../contracts/generated/contracts";
import type { AssistantChangeProposalV1 } from "../contracts/generated/contracts";
import type { AssistantConversationListV1 } from "../contracts/generated/contracts";
import type { AssistantConversationV1 } from "../contracts/generated/contracts";
import type { AssistantEventsV1 } from "../contracts/generated/contracts";
import type { AssistantMessagesV1 } from "../contracts/generated/contracts";
import type { AssistantRunRequestV2 } from "../contracts/generated/contracts";
import type { AssistantRunV1 } from "../contracts/generated/contracts";
import { ProjectApiFailure, v2Request, type Fetcher } from "../rich/v7-connection";

/** The /v2 assistant routes (D109). Replies are parsed with JSON.parse and typed; the server validated them. */
export type AgentFlags = { allowEdits: boolean; allowWeb: boolean };
export { ProjectApiFailure as AgentApiFailure };
export type Proposal = AssistantChangeProposalV1;
export type Run = AssistantRunV1;

const defaultFetch: Fetcher = (input, init) => fetch(input, init);

export function assistantSettings(fetcher: Fetcher = defaultFetch): Promise<AgentSettings> {
  return v2Request<AgentSettings>("/v1/settings/assistant", "GET", undefined, fetcher);
}
export function saveAssistantSettings(value: AgentSettingsRequest, fetcher: Fetcher = defaultFetch): Promise<AgentSettings> {
  return v2Request<AgentSettings>("/v1/settings/assistant", "PUT", value, fetcher);
}

export class AssistantApi {
  readonly prefix: string;
  /** `prefix` serves another scope on the same handlers: the template assistant (D141). */
  constructor(readonly projectId: string, private readonly fetcher: Fetcher = defaultFetch, prefix?: string) {
    this.prefix = prefix ?? `/v2/projects/${encodeURIComponent(projectId)}/assistant`;
  }
  private request<T>(tail: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
    const fetcher: Fetcher = signal ? (input, init) => this.fetcher(input, { ...init, signal }) : this.fetcher;
    return v2Request<T>(this.prefix + tail, method, method === "GET" ? undefined : body ?? {}, fetcher);
  }
  settings(): Promise<AgentSettings> { return assistantSettings(this.fetcher); }
  saveSettings(value: AgentSettingsRequest): Promise<AgentSettings> { return saveAssistantSettings(value, this.fetcher); }
  capabilities(): Promise<AssistantCapabilitiesV1> { return this.request("/capabilities"); }
  conversations(): Promise<AssistantConversationListV1> { return this.request("/conversations"); }
  createConversation(): Promise<AssistantConversationV1> { return this.request("/conversations", "POST"); }
  messages(conversationId: string): Promise<AssistantMessagesV1> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/messages`);
  }
  submit(conversationId: string, request: AssistantRunRequestV2): Promise<AssistantRunV1> {
    return this.request(`/conversations/${encodeURIComponent(conversationId)}/runs`, "POST", request);
  }
  /** One long-poll: the server answers as soon as an event after `after` exists, or after its wait. */
  events(runId: string, after: number, signal?: AbortSignal): Promise<AssistantEventsV1> {
    return this.request(`/runs/${encodeURIComponent(runId)}/events/${String(after)}`, "GET", undefined, signal);
  }
  cancel(runId: string): Promise<AssistantRunV1> { return this.request(`/runs/${encodeURIComponent(runId)}/cancel`, "POST"); }
  proposals(): Promise<AssistantChangeProposalListV1> { return this.request("/proposals"); }
  discard(proposalId: string): Promise<AssistantChangeProposalV1> {
    return this.request(`/proposals/${encodeURIComponent(proposalId)}/discard`, "POST");
  }
}
