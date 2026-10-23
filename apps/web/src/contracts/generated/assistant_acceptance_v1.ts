export type Acceptanceid = string;
export type Contentsha256 = string;
export type Epoch = number;
export type Token = string;
export type Proposalid = string;
export type Protocolversion = 1;
export type Schemaversion = 1;
export type Version = number;

export interface AssistantAcceptanceV1 {
  acceptanceId: Acceptanceid;
  contentSha256: Contentsha256;
  owner: AgentOwner;
  proposalId: Proposalid;
  protocolVersion: Protocolversion;
  schemaVersion?: Schemaversion;
  version: Version;
}
export interface AgentOwner {
  epoch: Epoch;
  token: Token;
}
