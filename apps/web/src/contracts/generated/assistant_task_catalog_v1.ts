export type Catalogrevision = string;
export type Editorfamily = "ordinary" | "template";
export type Lineage = string;
export type Projectid = string;
export type Protocolenabled = boolean;
export type Protocolversion = 1;
export type Schemaversion = 1;
/**
 * @minItems 1
 * @maxItems 32
 */
export type Tasks = [AssistantTaskV1, ...AssistantTaskV1[]];
export type Reason = string | null;
export type Reasoncode = string | null;
export type Remedy = string | null;
export type State = "available" | "permission_disabled" | "missing_input" | "temporarily_unavailable" | "unsupported";
/**
 * @maxItems 2
 */
export type Editors = [] | ["ordinary" | "template"] | ["ordinary" | "template", "ordinary" | "template"];
export type Effect = "read" | "proposal" | "project_action" | "export";
export type Id =
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
export type Label = string;
export type Prompt = string | null;
/**
 * @maxItems 8
 */
export type Requiredinputs =
  | []
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string];
/**
 * @maxItems 3
 */
export type Requiredpermissions =
  | []
  | ["read" | "edit" | "internet"]
  | ["read" | "edit" | "internet", "read" | "edit" | "internet"]
  | ["read" | "edit" | "internet", "read" | "edit" | "internet", "read" | "edit" | "internet"];
export type Reversibility = "none" | "shared_undo" | "action_specific" | "artifact";
/**
 * @minItems 1
 * @maxItems 4
 */
export type Scopes =
  | ["resume" | "selection" | "project" | "chat"]
  | ["resume" | "selection" | "project" | "chat", "resume" | "selection" | "project" | "chat"]
  | [
      "resume" | "selection" | "project" | "chat",
      "resume" | "selection" | "project" | "chat",
      "resume" | "selection" | "project" | "chat"
    ]
  | [
      "resume" | "selection" | "project" | "chat",
      "resume" | "selection" | "project" | "chat",
      "resume" | "selection" | "project" | "chat",
      "resume" | "selection" | "project" | "chat"
    ];

export interface AssistantTaskCatalogV1 {
  catalogRevision: Catalogrevision;
  editorFamily: Editorfamily;
  lineage: Lineage;
  projectId: Projectid;
  protocolEnabled: Protocolenabled;
  protocolVersion?: Protocolversion;
  schemaVersion?: Schemaversion;
  tasks: Tasks;
}
export interface AssistantTaskV1 {
  apply: AssistantAvailabilityV1;
  editors: Editors;
  effect: Effect;
  generation: AssistantAvailabilityV1;
  id: Id;
  label: Label;
  limits: Limits;
  preparation: AssistantAvailabilityV1;
  prompt: Prompt;
  requiredInputs: Requiredinputs;
  requiredPermissions: Requiredpermissions;
  reversibility: Reversibility;
  review: AssistantAvailabilityV1;
  scopes: Scopes;
}
export interface AssistantAvailabilityV1 {
  reason: Reason;
  reasonCode: Reasoncode;
  remedy: Remedy;
  state: State;
}
export interface Limits {
  [k: string]: number;
}
