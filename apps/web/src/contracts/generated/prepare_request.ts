export type Languages = string[];
export type Name = string;
export type Sourcelanguage = "ru" | "en" | "mixed";
export type Title = string;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Createdat = string;
export type Employer = string;
export type Factids = string[];
export type Id = string;
export type Periods = Period[];
export type Role = string;
export type Factids1 = string[];
export type Id1 = string;
export type Name1 = string;
export type Subprojects = Subproject[];
export type Employment = Job[];
export type Sourceid = string;
export type Sourcerevision = number;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = Evidence1[];
export type Id2 = string;
export type Importance = "essential" | "normal" | "minor";
export type Jobid = string | null;
export type Kind = "text";
export type Origin = "source" | "user";
export type Revision = number;
export type Subprojectid = string | null;
export type Text = string;
export type Evidence2 = Evidence1[];
export type Id3 = string;
export type Importance1 = "essential" | "normal" | "minor";
export type Jobid1 = string | null;
export type Kind1 = "technology";
export type Origin1 = "source" | "user";
export type Revision1 = number;
export type Subprojectid1 = string | null;
export type Canonicalid = string;
export type Display = string;
export type Scope = "global" | "job" | "subproject";
export type Evidence3 = Evidence1[];
export type Id4 = string;
export type Importance2 = "essential" | "normal" | "minor";
export type Jobid2 = string | null;
export type Kind2 = "metric";
export type Origin2 = "source" | "user";
export type Revision2 = number;
export type Subprojectid2 = string | null;
export type Attribution = "personal" | "team" | "organization" | "unknown";
export type Baseline = string | null;
export type Comparator = "exact" | "at_least" | "at_most" | "approximately" | "range";
export type Number = number;
export type Period1 = string | null;
export type Qualifiers = string[];
export type Result = string | null;
export type Scope1 = string | null;
export type Unit = string;
export type Uppernumber = number | null;
export type Evidence4 = Evidence1[];
export type Id5 = string;
export type Importance3 = "essential" | "normal" | "minor";
export type Jobid3 = string | null;
export type Kind3 = "leadership";
export type Origin3 = "source" | "user";
export type Revision3 = number;
export type Subprojectid3 = string | null;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Evidence5 = Evidence1[];
export type Id6 = string;
export type Importance4 = "essential" | "normal" | "minor";
export type Jobid4 = string | null;
export type Kind4 = "date";
export type Origin4 = "source" | "user";
export type Revision4 = number;
export type Subprojectid4 = string | null;
export type Facts = (TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact)[];
export type Baserevision = number;
export type Captureddocumentrevision = number | null;
export type Dependencyfingerprint = string;
export type Documentrevision = number;
export type Projectrevision = number;
export type Rulessha256 = string | null;
export type Sourcefingerprint = string;
export type Errorcode = string | null;
export type Requestid = string;
export type Sequence = number;
export type Stage = string | null;
export type Type =
  | "operation.started"
  | "stage.changed"
  | "result.ready"
  | "usage.updated"
  | "operation.completed"
  | "operation.failed"
  | "cancelled";
export type Internalinferencerequests = number | null;
export type Logicalattempts = number;
export type Reportedinputtokens = number | null;
export type Reportedoutputtokens = number | null;
export type Events = OperationEvent[];
export type Id7 = string;
export type Kind5 =
  | "extract"
  | "validate"
  | "render"
  | "project_save"
  | "normalize_semantics"
  | "draft_prose"
  | "rewrite_prose"
  | "reconcile_edits";
export type Projectid = string | null;
export type Resultfingerprint = string | null;
export type Markdown = string;
export type Revision5 = number;
export type Sha256 = string;
export type Status = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Targetfieldids = string[];
export type Operations = Operation[];
export type Projectid1 = string;
export type Baseblockrevision = number;
export type Blockid = string;
export type Dependencyhash = string;
export type Evidencefactids = string[];
export type Findings = string[];
export type Id8 = string;
export type Kind6 = "draft_prose" | "rewrite_prose";
export type Operationid = string;
export type Replacementtext = string;
export type Proposals = Proposal[];
export type Blockid1 = string;
export type Blockrevision = number;
export type Text1 = string;
export type Blocks = RenderBlock[];
export type Path = string;
export type Sha2561 = string;
export type Size = number;
export type Id9 = string;
export type Projectrevision1 = number;
export type Rendererversion = string;
export type Snapshotsha256 = string;
export type Templateid = string;
export type Templateversion = string;
export type Renders = RenderSnapshot[];
export type Issueid = string;
export type Targetid = string;
export type Targetkind = "fact" | "block";
export type Targetrevision = number;
export type Acknowledgments = Acknowledgment[];
export type Disposition = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "excluded";
export type Reason = string | null;
export type Targetid1 = string;
export type Targetkind1 = "source_unit" | "fact" | "block";
export type Targetrevision1 = number;
export type Decisions = ReviewDecision[];
export type Revision6 = number;
export type Schemaversion = 3;
export type Byteref = string;
export type Bytesha256 = string;
export type Id10 = string;
export type Mimetype = string;
export type Originalname = string;
export type Id11 = string;
export type Origin5 = "user";
export type Revision7 = number;
export type Text2 = string;
export type Unitid1 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision8 = number;
export type Disposition1 = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id12 = string;
export type Column = number | null;
export type Index = number;
export type Kind7 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order = number;
export type Representedfactids = string[];
export type Revision9 = number;
export type Text3 = string;
export type Units = SourceUnit[];
export type Code = string;
export type Page = number | null;
export type Warningdetails = SourceWarning[];
export type Warnings = string[];
export type Sources = Source[];
export type Assets = AssetRef[];
export type Contentpolicyversion = string;
export type Id13 = string;
export type Packagesha256 = string;
export type Version = string;
export type Contentpolicyversion1 = string;
export type Dependencyhash1 = string;
export type Id14 = string;
export type Kind8 = "profile" | "job_prose" | "contact" | "focus" | "education" | "skills" | "early_career";
export type Factids2 = string[];
export type Locked = boolean;
export type Origin6 = "source" | "generated" | "manual";
export type Text4 = string;
export type Revision10 = number;
export type Status1 = "empty" | "running" | "proposed" | "ready" | "stale" | "error";
export type Visible = boolean;
export type Views = Block[];

export interface PrepareRequest {
  presentation: Presentation;
  project: Project;
}
export interface Presentation {
  jobProseBlocks: Jobproseblocks;
  languages?: Languages;
  name: Name;
  sourceLanguage: Sourcelanguage;
  title: Title;
}
export interface Jobproseblocks {
  [k: string]: string;
}
export interface Project {
  asOf: PartialDate | null;
  createdAt: Createdat;
  employment: Employment;
  facts: Facts;
  operations: Operations;
  projectId: Projectid1;
  proposals: Proposals;
  renders: Renders;
  review: Review;
  revision: Revision6;
  schemaVersion: Schemaversion;
  sources: Sources;
  template: TemplateManifest | null;
  views: Views;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface Job {
  employer: Employer;
  factIds: Factids;
  id: Id;
  periods: Periods;
  role: Role;
  subprojects: Subprojects;
}
export interface Period {
  end: PartialDate | null;
  start: PartialDate;
}
export interface Subproject {
  factIds: Factids1;
  id: Id1;
  name: Name1;
  period: Period | null;
}
export interface TextFact {
  evidence: Evidence;
  id: Id2;
  importance: Importance;
  jobId: Jobid;
  kind: Kind;
  origin: Origin;
  revision: Revision;
  subprojectId: Subprojectid;
  value: TextValue;
}
export interface Evidence1 {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface TextValue {
  text: Text;
}
export interface TechnologyFact {
  evidence: Evidence2;
  id: Id3;
  importance: Importance1;
  jobId: Jobid1;
  kind: Kind1;
  origin: Origin1;
  revision: Revision1;
  subprojectId: Subprojectid1;
  value: TechnologyValue;
}
export interface TechnologyValue {
  canonicalId: Canonicalid;
  display: Display;
  scope: Scope;
}
export interface MetricFact {
  evidence: Evidence3;
  id: Id4;
  importance: Importance2;
  jobId: Jobid2;
  kind: Kind2;
  origin: Origin2;
  revision: Revision2;
  subprojectId: Subprojectid2;
  value: MetricValue;
}
export interface MetricValue {
  attribution: Attribution;
  baseline: Baseline;
  comparator: Comparator;
  number: Number;
  period: Period1;
  qualifiers: Qualifiers;
  result: Result;
  scope: Scope1;
  unit: Unit;
  upperNumber: Uppernumber;
}
export interface LeadershipFact {
  evidence: Evidence4;
  id: Id5;
  importance: Importance3;
  jobId: Jobid3;
  kind: Kind3;
  origin: Origin3;
  revision: Revision3;
  subprojectId: Subprojectid3;
  value: LeadershipValue;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface DateFact {
  evidence: Evidence5;
  id: Id6;
  importance: Importance4;
  jobId: Jobid4;
  kind: Kind4;
  origin: Origin4;
  revision: Revision4;
  subprojectId: Subprojectid4;
  value: PartialDate;
}
export interface Operation {
  baseRevision: Baserevision;
  capturedDocumentRevision?: Captureddocumentrevision;
  dependencies?: OperationDependencies | null;
  errorCode?: Errorcode;
  events: Events;
  id: Id7;
  kind: Kind5;
  projectId?: Projectid;
  resultFingerprint?: Resultfingerprint;
  rulesUsed?: OperationRules | null;
  status: Status;
  targetFieldIds?: Targetfieldids;
  usage: Usage | null;
}
export interface OperationDependencies {
  dependencyFingerprint: Dependencyfingerprint;
  documentRevision: Documentrevision;
  projectRevision: Projectrevision;
  rulesSha256: Rulessha256;
  sourceFingerprint: Sourcefingerprint;
}
export interface OperationEvent {
  requestId: Requestid;
  sequence: Sequence;
  stage: Stage;
  type: Type;
  usage: Usage | null;
}
export interface Usage {
  internalInferenceRequests: Internalinferencerequests;
  logicalAttempts: Logicalattempts;
  reportedInputTokens: Reportedinputtokens;
  reportedOutputTokens: Reportedoutputtokens;
}
export interface OperationRules {
  markdown: Markdown;
  revision: Revision5;
  sha256: Sha256;
}
export interface Proposal {
  baseBlockRevision: Baseblockrevision;
  blockId: Blockid;
  dependencyHash: Dependencyhash;
  evidenceFactIds: Evidencefactids;
  findings: Findings;
  id: Id8;
  kind: Kind6;
  operationId: Operationid;
  replacementText: Replacementtext;
}
export interface RenderSnapshot {
  blocks: Blocks;
  docx: AssetRef | null;
  id: Id9;
  pdf: AssetRef | null;
  projectRevision: Projectrevision1;
  rendererVersion: Rendererversion;
  snapshotSha256: Snapshotsha256;
  templateId: Templateid;
  templateVersion: Templateversion;
}
export interface RenderBlock {
  blockId: Blockid1;
  blockRevision: Blockrevision;
  text: Text1;
}
export interface AssetRef {
  path: Path;
  sha256: Sha2561;
  size: Size;
}
export interface Review {
  acknowledgments: Acknowledgments;
  decisions: Decisions;
}
export interface Acknowledgment {
  issueId: Issueid;
  targetId: Targetid;
  targetKind: Targetkind;
  targetRevision: Targetrevision;
}
export interface ReviewDecision {
  disposition: Disposition;
  reason: Reason;
  targetId: Targetid1;
  targetKind: Targetkind1;
  targetRevision: Targetrevision1;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id10;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision8;
  units: Units;
  warningDetails?: Warningdetails;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id11;
  origin: Origin5;
  revision: Revision7;
  text: Text2;
  unitId: Unitid1;
}
export interface SourceUnit {
  disposition: Disposition1;
  id: Id12;
  location: SourceLocation;
  order: Order;
  representedFactIds: Representedfactids;
  revision: Revision9;
  text: Text3;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind7;
  row: Row;
}
export interface SourceWarning {
  code: Code;
  page?: Page;
}
export interface TemplateManifest {
  assets: Assets;
  contentPolicyVersion: Contentpolicyversion;
  id: Id13;
  packageSha256: Packagesha256;
  version: Version;
}
export interface Block {
  contentPolicyVersion: Contentpolicyversion1;
  dependencyHash: Dependencyhash1;
  id: Id14;
  kind: Kind8;
  previous: BlockState | null;
  revision: Revision10;
  state: BlockState;
  status: Status1;
  visible: Visible;
}
export interface BlockState {
  factIds: Factids2;
  factRevisions: Factrevisions;
  locked: Locked;
  origin: Origin6;
  text: Text4;
}
export interface Factrevisions {
  [k: string]: number;
}
