export type Actioncursor = number;
export type Canonicalrevision = number;
export type Canonicalsha256 = string;
export type Credential = string;
export type Draftsequence = number;
export type Incarnation = string;
export type Previousepoch = number | null;
export type Previousincarnation = string | null;
export type Schemaversion = 1;
export type Sessionid = string;

export interface WriterOpenV1 {
  actionCursor: Actioncursor;
  canonicalRevision: Canonicalrevision;
  canonicalSha256: Canonicalsha256;
  credential: Credential;
  draftSequence?: Draftsequence;
  incarnation: Incarnation;
  previousEpoch?: Previousepoch;
  previousIncarnation?: Previousincarnation;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
}
