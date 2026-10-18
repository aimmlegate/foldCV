export type Expectedrevision = number;
export type Readonly = boolean;

export interface AgentAccessRequest {
  expectedRevision: Expectedrevision;
  readOnly: Readonly;
}
