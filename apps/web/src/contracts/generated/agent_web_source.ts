export type Contentsha256 = string;
export type Finalurl = string;
export type Id = string;
export type Originalbytes = number;
export type Requestedurl = string;
export type Retrievedat = string;
export type Runid = string;
export type Text = string;
export type Title = string;
export type Truncated = boolean;

export interface AgentWebSource {
  contentSha256: Contentsha256;
  finalUrl: Finalurl;
  id: Id;
  originalBytes: Originalbytes;
  requestedUrl: Requestedurl;
  retrievedAt: Retrievedat;
  runId: Runid;
  text: Text;
  title: Title;
  truncated: Truncated;
}
