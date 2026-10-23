export type Cursor = string | null;
export type Proposalid = string;
export type Protocolversion = 1;
export type Schemaversion = 1;
export type Version = number;

export interface AssistantDraftReadV1 {
  cursor?: Cursor;
  proposalId: Proposalid;
  protocolVersion: Protocolversion;
  schemaVersion?: Schemaversion;
  version: Version;
}
