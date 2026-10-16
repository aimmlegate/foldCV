export type Canonicalrevision = number;
export type Canonicalsha256 = string;
export type Id = string;
export type Payloadsha256 = string;
export type Credential = string;
export type Epoch = number;
export type Incarnation = string;
export type Lineage = string;
export type Schemaversion = 1;
export type Sessionid = string;
export type Schemaversion1 = 1;
export type Sequence = number;

export interface WriterDraftCommandV1 {
  canonicalRevision: Canonicalrevision;
  canonicalSha256: Canonicalsha256;
  id: Id;
  payloadSha256: Payloadsha256;
  proof: WriterProofV1;
  schemaVersion: Schemaversion1;
  sequence: Sequence;
}
export interface WriterProofV1 {
  credential: Credential;
  epoch: Epoch;
  incarnation: Incarnation;
  lineage: Lineage;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
}
