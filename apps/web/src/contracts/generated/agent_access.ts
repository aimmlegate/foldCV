export type Readonly = boolean;
export type Revision = number;

export interface AgentAccess {
  readOnly: Readonly;
  revision: Revision;
}
