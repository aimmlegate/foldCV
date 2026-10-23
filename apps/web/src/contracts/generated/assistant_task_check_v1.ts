export type Reason = string | null;
export type Reasoncode = string | null;
export type Remedy = string | null;
export type State = "available" | "permission_disabled" | "missing_input" | "temporarily_unavailable" | "unsupported";
export type Catalogrevision = string;
export type Needsplanning = boolean;
export type Projectid = string;
export type Protocolversion = 1;
export type Schemaversion = 1;
export type Taskid =
  | (
      | "read_resume"
      | "check_resume"
      | "draft_text"
      | "rewrite_resume"
      | "correct_facts"
      | "restructure"
      | "format_document"
      | "project_metadata"
      | "sources"
      | "images"
      | "archive_project"
      | "restore_project"
      | "delete_project"
      | "undo"
      | "redo"
      | "export_docx"
      | "export_project"
      | "read_public_page"
      | "export_pdf"
      | "shell"
      | "apps"
      | "send_application"
      | "import_resume"
    )
  | null;

export interface AssistantTaskCheckV1 {
  availability: AssistantAvailabilityV1;
  catalogRevision: Catalogrevision;
  needsPlanning: Needsplanning;
  projectId: Projectid;
  protocolVersion?: Protocolversion;
  schemaVersion?: Schemaversion;
  taskId: Taskid;
}
export interface AssistantAvailabilityV1 {
  reason: Reason;
  reasonCode: Reasoncode;
  remedy: Remedy;
  state: State;
}
