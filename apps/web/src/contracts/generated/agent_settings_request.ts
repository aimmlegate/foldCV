export type Enabled = boolean;
export type Expectedrevision = number;
export type Selectedagentmodel = string | null;

export interface AgentSettingsRequest {
  enabled: Enabled;
  expectedRevision: Expectedrevision;
  selectedAgentModel: Selectedagentmodel;
}
