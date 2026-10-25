export type Acceptanceid = string;
export type Contentsha256 = string;
export type Proposalid = string;
export type Protocolversion = 1;
export type Schemaversion = 1;
export type Version = number;
export type Expiresat = string;
export type Protocolversion1 = 1;
export type Requestsha256 = string;
export type Schemaversion1 = 1;
export type Ticket = string;

export interface AssistantProjectActionClaimV1 {
  accepted: AssistantAcceptanceIdentityV1;
  expiresAt: Expiresat;
  protocolVersion?: Protocolversion1;
  requestSha256: Requestsha256;
  schemaVersion?: Schemaversion1;
  ticket: Ticket;
}
export interface AssistantAcceptanceIdentityV1 {
  acceptanceId: Acceptanceid;
  contentSha256: Contentsha256;
  proposalId: Proposalid;
  protocolVersion: Protocolversion;
  schemaVersion?: Schemaversion;
  version: Version;
}
