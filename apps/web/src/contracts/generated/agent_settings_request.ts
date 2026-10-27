export type Enabled = boolean;
export type Expectedrevision = number;
export type Reasoningeffort = ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Selectedagentmodel = string | null;

export interface AgentSettingsRequest {
  enabled: Enabled;
  expectedRevision: Expectedrevision;
  reasoningEffort?: Reasoningeffort;
  selectedAgentModel: Selectedagentmodel;
}
