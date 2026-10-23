export type Contentsha256 = string;
export type Proposalid = string;
export type Protocolversion = 1;
export type Schemaversion = 1;
export type Version = number;

export interface AssistantProposalRequestV1 {
  contentSha256: Contentsha256;
  proposalId: Proposalid;
  protocolVersion: Protocolversion;
  schemaVersion?: Schemaversion;
  version: Version;
}
