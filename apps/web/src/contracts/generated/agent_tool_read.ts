export type Cursor = string | null;
/**
 * @maxItems 100
 */
export type Ids = string[];
export type Kind = "context" | "document" | "find" | "facts" | "source" | "history" | "resources";
export type Parentid = string | null;
export type Text = string;

export interface AgentToolRead {
  query: AgentQuery;
}
export interface AgentQuery {
  cursor?: Cursor;
  ids?: Ids;
  kind: Kind;
  parentId?: Parentid;
  text?: Text;
}
