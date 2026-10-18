export type Action =
  | "rename"
  | "formatting_date"
  | "add_source_text"
  | "remove_source"
  | "import_asset"
  | "remove_asset"
  | "export_docx"
  | "export_project"
  | "archive"
  | "restore"
  | "delete"
  | "undo"
  | "redo";
export type Key = string;
export type Snapshotid = string;
export type Targetid = string | null;
export type Value = string;

export interface AgentProjectAction {
  action: Action;
  key: Key;
  snapshotId: Snapshotid;
  targetId?: Targetid;
  value?: Value;
}
