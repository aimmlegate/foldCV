export type Allowedits = boolean;
export type Allowweb = boolean;
export type Baserevision = number;
export type Clientrequestid = string;
export type Conversationid = string;
export type Createdat = string;
export type Code = string;
/**
 * @maxItems 20
 */
export type Detail =
  | []
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ];
export type Finishedat = string | null;
export type Id = string;
export type Model = string;
export type Projectid = string;
export type State = "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled" | "interrupted";
export type Cachedinputtokens = number;
export type Inputtokens = number;
export type Outputtokens = number;
export type Totaltokens = number;

export interface AssistantRunV1 {
  allowEdits: Allowedits;
  allowWeb: Allowweb;
  baseRevision: Baserevision;
  clientRequestId: Clientrequestid;
  conversationId: Conversationid;
  createdAt: Createdat;
  error: AssistantErrorV1 | null;
  finishedAt: Finishedat;
  id: Id;
  model: Model;
  projectId: Projectid;
  state: State;
  usage: AgentUsage | null;
}
export interface AssistantErrorV1 {
  code: Code;
  detail?: Detail;
}
export interface AgentUsage {
  cachedInputTokens: Cachedinputtokens;
  inputTokens: Inputtokens;
  outputTokens: Outputtokens;
  totalTokens: Totaltokens;
}
