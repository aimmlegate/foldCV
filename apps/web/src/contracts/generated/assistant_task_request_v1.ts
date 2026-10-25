export type Inputavailable = boolean;
export type Protocolversion = 1;
export type Schemaversion = 1;
export type Scope = "resume" | "selection" | "project" | "chat";
export type Stage = "generation" | "preparation" | "review" | "apply";
export type Taskid =
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
  | "import_resume";

export interface AssistantTaskRequestV1 {
  inputAvailable?: Inputavailable;
  protocolVersion: Protocolversion;
  schemaVersion?: Schemaversion;
  scope?: Scope;
  stage?: Stage;
  taskId: Taskid;
}
