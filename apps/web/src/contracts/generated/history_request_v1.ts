export type Baserevision = number;
export type Clientmutationid = string;
export type Direction = "undo" | "redo";
export type Editortoken = string;
export type Expectedactionid = string | null;

export interface HistoryRequestV1 {
  baseRevision: Baserevision;
  clientMutationId: Clientmutationid;
  direction: Direction;
  editorToken: Editortoken;
  expectedActionId: Expectedactionid;
}
