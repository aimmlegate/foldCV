export type Canonicalrevision = number;
export type Canonicalsha256 = string;
export type Credential = string;
/**
 * @maxItems 100
 */
export type Discarddrafts = string[];
export type Incarnation = string;
export type Schemaversion = 1;
export type Sessionid = string;

export interface WriterAbandonV1 {
  canonicalRevision: Canonicalrevision;
  canonicalSha256: Canonicalsha256;
  credential: Credential;
  discardDrafts?: Discarddrafts;
  incarnation: Incarnation;
  schemaVersion: Schemaversion;
  sessionId: Sessionid;
}
