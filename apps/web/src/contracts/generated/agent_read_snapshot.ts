export type Contentsha256 = string;
export type Kind = "entity";
export type Fingerprint = string | null;
export type Id = string;
export type Kind1 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
export type Fingerprint1 = string;
export type Kind2 = "query";
export type Cursor = string | null;
/**
 * @maxItems 100
 */
export type Ids = string[];
export type Kind3 = "context" | "document" | "find" | "facts" | "source" | "history";
export type Parentid = string | null;
export type Text = string;
/**
 * @maxItems 2000
 */
export type Dependencies = (AgentEntityDependency | AgentQueryDependency)[];
export type Id1 = string;
export type Nextcursor = string | null;
export type Runid = string;
export type Truncated = boolean;

export interface AgentReadSnapshot {
  contentSha256: Contentsha256;
  dependencies: Dependencies;
  id: Id1;
  nextCursor: Nextcursor;
  runId: Runid;
  truncated: Truncated;
}
export interface AgentEntityDependency {
  kind: Kind;
  stamp: DependencyStamp;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id;
  kind: Kind1;
  revision: Revision;
}
export interface AgentQueryDependency {
  fingerprint: Fingerprint1;
  kind: Kind2;
  query: AgentQuery;
}
export interface AgentQuery {
  cursor?: Cursor;
  ids?: Ids;
  kind: Kind3;
  parentId?: Parentid;
  text?: Text;
}
