export type Enabled = boolean;
export type Revision = number;
export type Schemaversion = 1;
export type Selectedagentmodel = string | null;

export interface AgentSettings {
  enabled: Enabled;
  revision: Revision;
  schemaVersion: Schemaversion;
  selectedAgentModel: Selectedagentmodel;
}
