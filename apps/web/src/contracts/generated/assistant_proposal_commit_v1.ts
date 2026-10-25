export type Contentsha256 = string;
export type Epoch = number;
export type Token = string;
export type Proposalid = string;
export type Protocolversion = 1;
export type Requestsha256 = string;
export type Schemaversion = 1;
export type Ticket = string;
export type Version = number;

export interface AssistantProposalCommitV1 {
  contentSha256: Contentsha256;
  owner: AgentOwner;
  proposalId: Proposalid;
  protocolVersion: Protocolversion;
  requestSha256: Requestsha256;
  schemaVersion?: Schemaversion;
  ticket: Ticket;
  version: Version;
}
export interface AgentOwner {
  epoch: Epoch;
  token: Token;
}
