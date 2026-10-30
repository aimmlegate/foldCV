export type Enabled = boolean;
export type Reasoningeffort = ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Revision = number;
export type Schemaversion = 1;
export type Selectedagentmodel = string | null;

export interface AgentSettings {
  enabled: Enabled;
  reasoningEffort?: Reasoningeffort;
  revision: Revision;
  schemaVersion: Schemaversion;
  selectedAgentModel: Selectedagentmodel;
}
