export type Clipboardcaptureid = string;
export type Credential = string;
export type Epoch = number;
export type Incarnation = string;
export type Lineage = string;
export type Schemaversion = 1;
export type Sessionid = string;
export type Schemaversion1 = 2;

export interface WriterReleaseClipboardV2 {
  clipboardCaptureId: Clipboardcaptureid;
  proof: WriterProofV1;
  schemaVersion: Schemaversion1;
}
export interface WriterProofV1 {
  credential: Credential;
  epoch: Epoch;
  incarnation: Incarnation;
  lineage: Lineage;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
}
