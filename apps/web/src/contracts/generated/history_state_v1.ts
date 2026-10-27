export type Actionid = string;
export type Kind = "edit";

export interface HistoryStateV1 {
  redo: HistoryActionV1 | null;
  undo: HistoryActionV1 | null;
}
export interface HistoryActionV1 {
  actionId: Actionid;
  kind: Kind;
}
