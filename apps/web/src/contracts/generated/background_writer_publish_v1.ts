export type Approve = boolean;
export type Generation = number;
export type Jobid = string;
export type Credential = string;
export type Epoch = number;
export type Incarnation = string;
export type Lineage = string;
export type Schemaversion = 1;
export type Sessionid = string;
export type Proposalsha256 = string;
export type Schemaversion1 = 1;
export type Token = string;

export interface WriterPublishV1 {
  approve?: Approve;
  generation: Generation;
  jobId: Jobid;
  proof: WriterProofV1;
  proposalSha256: Proposalsha256;
  schemaVersion: Schemaversion1;
  token: Token;
}
export interface WriterProofV1 {
  credential: Credential;
  epoch: Epoch;
  incarnation: Incarnation;
  lineage: Lineage;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
}
