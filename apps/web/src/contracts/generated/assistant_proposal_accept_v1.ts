export type Contentsha256 = string;
export type Epoch = number;
export type Token = string;
export type Proposalid = string;
export type Protocolversion = 1;
export type Schemaversion = 1;
export type Version = number;

export interface AssistantProposalAcceptV1 {
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
