export type Action =
  | "rename"
  | "formatting_date"
  | "add_source_text"
  | "remove_source"
  | "import_asset"
  | "remove_asset"
  | "archive"
  | "restore"
  | "delete";
export type Consequence = string;
export type Imagepreviewurl = string | null;
export type Protocolversion = 1;
export type Schemaversion = 1;
export type Targetid = string;
export type Targetlabel = string;
export type Reason = string | null;
export type Reasoncode = string | null;
export type Remedy = string | null;
export type State = "available" | "permission_disabled" | "missing_input" | "temporarily_unavailable" | "unsupported";
export type Generationfinished = boolean;
export type Beforesha256 = string;
export type After = string;
export type Before = string;
export type Effect = "wording" | "structure" | "fact" | "format";
export type Protocolversion1 = 1;
export type Schemaversion1 = 1;
export type Unitid = string;
/**
 * @maxItems 2000
 */
export type Changes = AssistantChangeV1[];
export type Contentsha256 = string;
export type Protocolversion2 = 1;
export type Read = boolean;
export type Reason1 = string;
export type Schemaversion2 = 1;
export type State1 = "changed" | "unchanged" | "unresolved";
export type Unitid1 = string;
/**
 * @maxItems 20000
 */
export type Coverage = AssistantCoverageV1[];
export type Createdat = string;
export type Editorfamily = "ordinary";
export type Expiresat = string;
export type Id = string;
export type Lineage = string;
export type Operationcount = number;
export type Originrequestid = string;
export type Originrunid = string;
export type Projectid = string;
export type Protocolversion3 = 1;
export type Reason2 = string | null;
export type Schemaversion3 = 1;
export type State2 =
  | "building"
  | "ready"
  | "incomplete"
  | "invalid"
  | "cancelled"
  | "applying"
  | "applied"
  | "stale"
  | "discarded"
  | "expired"
  | "failed_before_commit"
  | "outcome_unknown";
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
export type Version = number;
export type Protocolversion4 = 1;
export type Schemaversion4 = 1;

export interface AssistantCapabilityReviewV1 {
  action?: AssistantProjectActionPreviewV1 | null;
  apply: AssistantAvailabilityV1;
  generationFinished: Generationfinished;
  proposal: AssistantProposalV1;
  protocolVersion?: Protocolversion4;
  schemaVersion?: Schemaversion4;
}
export interface AssistantProjectActionPreviewV1 {
  action: Action;
  consequence: Consequence;
  imagePreviewUrl?: Imagepreviewurl;
  protocolVersion?: Protocolversion;
  schemaVersion?: Schemaversion;
  targetId: Targetid;
  targetLabel: Targetlabel;
}
export interface AssistantAvailabilityV1 {
  reason: Reason;
  reasonCode: Reasoncode;
  remedy: Remedy;
  state: State;
}
export interface AssistantProposalV1 {
  beforeSha256: Beforesha256;
  changes: Changes;
  contentSha256: Contentsha256;
  coverage: Coverage;
  createdAt: Createdat;
  editorFamily: Editorfamily;
  expiresAt: Expiresat;
  id: Id;
  lineage: Lineage;
  operationCount: Operationcount;
  originRequestId: Originrequestid;
  originRunId: Originrunid;
  projectId: Projectid;
  protocolVersion?: Protocolversion3;
  reason: Reason2;
  schemaVersion?: Schemaversion3;
  state: State2;
  taskId: Taskid;
  version: Version;
}
export interface AssistantChangeV1 {
  after: After;
  before: Before;
  effect: Effect;
  protocolVersion?: Protocolversion1;
  schemaVersion?: Schemaversion1;
  unitId: Unitid;
}
export interface AssistantCoverageV1 {
  protocolVersion?: Protocolversion2;
  read: Read;
  reason: Reason1;
  schemaVersion?: Schemaversion2;
  state: State1;
  unitId: Unitid1;
}
