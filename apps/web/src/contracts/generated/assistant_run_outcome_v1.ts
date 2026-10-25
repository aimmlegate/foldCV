export type Durable = boolean;
export type Outcome =
  "none" | "no_change" | "draft_ready" | "incomplete" | "applied" | "stale" | "failed" | "outcome_unknown";
export type Protocolversion = 1;
export type Reason = string;
export type Runid = string;
export type Schemaversion = 1;

export interface AssistantRunOutcomeV1 {
  durable: Durable;
  outcome: Outcome;
  protocolVersion?: Protocolversion;
  reason: Reason;
  runId: Runid;
  schemaVersion?: Schemaversion;
}
