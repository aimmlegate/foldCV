export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Createdat = string;
export type Id = "candidate";
export type Kind = "candidate";
export type Sourceid = string;
export type Sourcerevision = number;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = Evidence1[];
export type Factids = string[];
export type Fieldid = string;
export type Origin = "source" | "generated" | "user" | "migration";
export type Text = string;
export type Revision = number;
export type Visible = true;
export type Id1 = string;
export type Kind1 = "certification";
export type Revision1 = number;
export type Visible1 = boolean;
export type Certifications = CertificationRecord[];
export type Id2 = "early-career";
export type Kind2 = "early-career";
export type Representedjobids = string[];
export type Revision2 = number;
export type Visible2 = boolean;
export type Id3 = string;
export type Kind3 = "education";
export type Revision3 = number;
export type Visible3 = boolean;
export type Education = EducationRecord[];
export type Id4 = string;
export type Kind4 = "job";
export type Id5 = string;
export type Present = boolean;
export type Periods = DocumentPeriod[];
export type Periodsfieldid = string;
export type Revision4 = number;
export type Subprojectids = string[];
export type Visible4 = boolean;
export type Jobs = JobRecord[];
export type Id6 = string;
export type Kind5 = "language";
export type Revision5 = number;
export type Visible5 = boolean;
export type Languages = LanguageRecord[];
export type Id7 = "profile";
export type Kind6 = "profile";
export type Revision6 = number;
export type Visible6 = boolean;
/**
 * @maxItems 8
 */
export type Focus =
  | []
  | [FocusEntry]
  | [FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry]
  | [FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry, FocusEntry];
export type Catalogid = string;
export type Factids1 = string[];
export type Id8 = string;
export type Focusfieldid = string;
export type Id9 = "skills-focus";
export type Kind7 = "skills-focus";
export type Revision7 = number;
export type Visible7 = boolean;
export type Employer = string;
export type Factids2 = string[];
export type Id10 = string;
export type Periods1 = Period[];
export type Role = string;
export type Factids3 = string[];
export type Id11 = string;
export type Name = string;
export type Subprojects = Subproject[];
export type Employment = Job[];
export type Evidence2 = Evidence1[];
export type Id12 = string;
export type Importance = "essential" | "normal" | "minor";
export type Jobid = string | null;
export type Kind8 = "text";
export type Sourceid1 = string;
export type Sourcerevision1 = number;
export type Text1 = string;
export type Unitid1 = string;
export type Unitrevision1 = number;
export type Literalevidence = EvidenceSpan[];
export type Origin1 = "source" | "user";
export type Revision8 = number;
export type Subprojectid = string | null;
export type Text2 = string;
export type Evidence3 = Evidence1[];
export type Id13 = string;
export type Importance1 = "essential" | "normal" | "minor";
export type Jobid1 = string | null;
export type Kind9 = "technology";
export type Literalevidence1 = EvidenceSpan[];
export type Origin2 = "source" | "user";
export type Revision9 = number;
export type Subprojectid1 = string | null;
export type Canonicalid = string;
export type Display = string;
export type Scope = "global" | "job" | "subproject";
export type Evidence4 = Evidence1[];
export type Id14 = string;
export type Importance2 = "essential" | "normal" | "minor";
export type Jobid2 = string | null;
export type Kind10 = "metric";
export type Literalevidence2 = EvidenceSpan[];
export type Origin3 = "source" | "user";
export type Revision10 = number;
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
export type Evidence5 = Evidence1[];
export type Id15 = string;
export type Importance3 = "essential" | "normal" | "minor";
export type Jobid3 = string | null;
export type Kind11 = "leadership";
export type Literalevidence3 = EvidenceSpan[];
export type Origin4 = "source" | "user";
export type Revision11 = number;
export type Subprojectid3 = string | null;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Evidence6 = Evidence1[];
export type Id16 = string;
export type Importance4 = "essential" | "normal" | "minor";
export type Jobid4 = string | null;
export type Kind12 = "date";
export type Literalevidence4 = EvidenceSpan[];
export type Origin5 = "source" | "user";
export type Revision12 = number;
export type Subprojectid4 = string | null;
export type Evidence7 = Evidence1[];
export type Id17 = string;
export type Importance5 = "essential" | "normal" | "minor";
export type Jobid5 = string | null;
export type Kind13 = "text";
export type Origin6 = "source" | "user";
export type Revision13 = number;
export type Subprojectid5 = string | null;
export type Evidence8 = Evidence1[];
export type Id18 = string;
export type Importance6 = "essential" | "normal" | "minor";
export type Jobid6 = string | null;
export type Kind14 = "technology";
export type Origin7 = "source" | "user";
export type Revision14 = number;
export type Subprojectid6 = string | null;
export type Evidence9 = Evidence1[];
export type Id19 = string;
export type Importance7 = "essential" | "normal" | "minor";
export type Jobid7 = string | null;
export type Kind15 = "metric";
export type Origin8 = "source" | "user";
export type Revision15 = number;
export type Subprojectid7 = string | null;
export type Evidence10 = Evidence1[];
export type Id20 = string;
export type Importance8 = "essential" | "normal" | "minor";
export type Jobid8 = string | null;
export type Kind16 = "leadership";
export type Origin9 = "source" | "user";
export type Revision16 = number;
export type Subprojectid8 = string | null;
export type Evidence11 = Evidence1[];
export type Id21 = string;
export type Importance9 = "essential" | "normal" | "minor";
export type Jobid9 = string | null;
export type Kind17 = "date";
export type Origin10 = "source" | "user";
export type Revision17 = number;
export type Subprojectid9 = string | null;
export type Evidence12 = Evidence1[];
export type Id22 = string;
export type Importance10 = "essential" | "normal" | "minor";
export type Jobid10 = string | null;
export type Kind18 = "candidate_detail";
export type Origin11 = "source" | "user";
export type Revision18 = number;
export type Subprojectid10 = string | null;
export type Field = "name" | "title" | "location" | "education" | "certification" | "language" | "private_metadata";
export type Fieldid1 = string | null;
export type Text3 = string;
export type Evidence13 = Evidence1[];
export type Id23 = string;
export type Importance11 = "essential" | "normal" | "minor";
export type Jobid11 = string | null;
export type Kind19 = "name_assessment";
export type Origin12 = "source" | "user";
export type Revision19 = number;
export type Subprojectid11 = string | null;
export type Evidence14 = EvidenceSpan[];
export type Missingsurname = boolean | null;
export type Revision20 = number;
export type Evidence15 = Evidence1[];
export type Id24 = string;
export type Importance12 = "essential" | "normal" | "minor";
export type Jobid12 = string | null;
export type Kind20 = "source_observation";
export type Origin13 = "source" | "user";
export type Revision21 = number;
export type Subprojectid12 = string | null;
export type Revision22 = number;
export type Evidence16 = Evidence1[];
export type Id25 = string;
export type Importance13 = "essential" | "normal" | "minor";
export type Jobid13 = string | null;
export type Kind21 = "employment";
export type Literalevidence5 = EvidenceSpan[];
export type Origin14 = "source" | "user";
export type Revision23 = number;
export type Subprojectid13 = string | null;
export type Employer1 = string;
export type Jobid14 = string;
export type Endtext = string;
export type Evidence17 = EvidenceSpan[];
export type Id26 = string;
export type Present1 = boolean;
export type Starttext = string;
export type Periods2 = EmploymentPeriodValue[];
export type Role1 = string;
export type Subprojects1 = Subproject[];
export type Facts = (
  | (GuiTextFact | GuiTechnologyFact | GuiMetricFact | GuiLeadershipFact | GuiDateFact)
  | (TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact)
  | CandidateFact
  | NameAssessmentFact
  | ObservationFact
  | EmploymentFact
)[];
export type Completedfieldids = string[];
export type Enabled = boolean;
export type Phase = "pending" | "dispatched";
export type Baserevision = number;
export type Captureddocumentrevision = number | null;
export type Dependencyfingerprint = string;
export type Documentrevision = number;
export type Projectrevision = number;
export type Rulessha256 = string | null;
export type Sourcefingerprint = string;
export type Anchor = FieldAnchor | SectionAnchor | DocumentAnchor;
export type Fieldid2 = string;
export type Kind22 = "field";
export type End = number;
export type Start = number;
export type Kind23 = "section";
export type Sectionid = string;
export type Kind24 = "document";
export type Code =
  | "DOCX_NAME_LINE_LIMIT"
  | "DOCX_TITLE_LINE_LIMIT"
  | "DOCX_UNBREAKABLE_TEXT"
  | "DOCX_BLOCK_PAGE_BUDGET"
  | "DOCX_BLOCK_PLANNED_PAGE"
  | "DOCX_UNKNOWN_FOCUS_ICON"
  | "DOCX_TEXT_LIMIT"
  | "DOCX_LIST_LIMIT"
  | "DOCX_TOTAL_TEXT_LIMIT"
  | "DOCX_INVALID_CHARACTER"
  | "DOCX_INVALID_RENDER_INPUT"
  | "DOCX_RENDER_FAILED";
export type Path = string | null;
export type Editorialrecommendations = string[];
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
export type Events = GuiOperationEvent[];
export type Id27 = string;
export type Kind25 =
  | "extract"
  | "validate"
  | "render"
  | "project_save"
  | "normalize_semantics"
  | "draft_prose"
  | "rewrite_prose"
  | "reconcile_edits";
export type Projectid = string;
export type Rendersnapshotid = string | null;
export type Resultfingerprint = string | null;
export type Markdown = string;
export type Revision24 = number;
export type Sha256 = string;
export type Status = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Targetfieldids = string[];
export type Operations = GuiOperation[];
export type Projectid1 = string;
export type Baseblockrevision = number;
export type Blockid = string;
export type Dependencyhash = string;
export type Evidencefactids = string[];
export type Findings = string[];
export type Id28 = string;
export type Kind26 = "draft_prose" | "rewrite_prose";
export type Operationid = string;
export type Replacementtext = string;
export type Proposals = Proposal[];
export type Artifactavailable = boolean;
export type Documentrevision1 = number;
export type Path1 = string;
export type Sha2561 = string;
export type Size = number;
export type Id29 = string;
export type Pdf = null;
export type Projectrevision1 = number;
export type Renderinputfingerprint = string;
export type Renderersha256 = string;
export type Rendererversion = string;
export type Templateid = string;
export type Templatesha256 = string;
export type Templateversion = string;
export type Renders = RenderSnapshotV4[];
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
export type Revision25 = number;
export type Schemaversion = 4;
export type Byteref = string;
export type Bytesha256 = string;
export type Id30 = string;
export type Mimetype = string;
export type Originalname = string;
export type Id31 = string;
export type Origin15 = "user";
export type Revision26 = number;
export type Text4 = string;
export type Unitid2 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision27 = number;
export type Disposition1 = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id32 = string;
export type Column = number | null;
export type Index = number;
export type Kind27 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order = number;
export type Representedfactids = string[];
export type Revision28 = number;
export type Text5 = string;
export type Units = SourceUnit[];
export type Warnings = string[];
export type Sources = Source[];
export type Assets = AssetRef[];
export type Contentpolicyversion = string;
export type Id33 = string;
export type Packagesha256 = string;
export type Version = string;
export type Contentpolicyversion1 = string;
export type Dependencyhash1 = string;
export type Id34 = string;
export type Kind28 = "profile" | "job_prose" | "contact" | "focus" | "education" | "skills" | "early_career";
export type Factids4 = string[];
export type Locked = boolean;
export type Origin16 = "source" | "generated" | "manual";
export type Text6 = string;
export type Revision29 = number;
export type Status1 = "empty" | "running" | "proposed" | "ready" | "stale" | "error";
export type Visible8 = boolean;
export type Views = Block[];

export interface ProjectV4 {
  asOf: PartialDate | null;
  createdAt: Createdat;
  document: Document;
  employment: Employment;
  facts: Facts;
  operations: Operations;
  projectId: Projectid1;
  proposals: Proposals;
  renders: Renders;
  review: Review;
  revision: Revision25;
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
export interface Document {
  candidate: CandidateRecord;
  certifications: Certifications;
  earlyCareer: EarlyCareerRecord;
  education: Education;
  jobs: Jobs;
  languages: Languages;
  profile: ProfileRecord;
  skillsFocus: SkillsFocusRecord;
}
export interface CandidateRecord {
  id: Id;
  kind: Kind;
  location: AuthoredField;
  name: AuthoredField;
  revision: Revision;
  title: AuthoredField;
  visible: Visible;
}
export interface AuthoredField {
  evidence: Evidence;
  factIds: Factids;
  fieldId: Fieldid;
  origin: Origin;
  text: Text;
}
export interface Evidence1 {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface CertificationRecord {
  dateText: AuthoredField;
  id: Id1;
  issuer: AuthoredField;
  kind: Kind1;
  legacyText: AuthoredField | null;
  name: AuthoredField;
  revision: Revision1;
  visible: Visible1;
}
export interface EarlyCareerRecord {
  id: Id2;
  kind: Kind2;
  representedJobIds: Representedjobids;
  revision: Revision2;
  text: AuthoredField;
  visible: Visible2;
}
export interface EducationRecord {
  dateText: AuthoredField;
  id: Id3;
  institution: AuthoredField;
  kind: Kind3;
  legacyText: AuthoredField | null;
  qualification: AuthoredField;
  revision: Revision3;
  specialty: AuthoredField;
  visible: Visible3;
}
export interface JobRecord {
  context: AuthoredField;
  employer: AuthoredField;
  id: Id4;
  kind: Kind4;
  periods: Periods;
  periodsFieldId: Periodsfieldid;
  results: AuthoredField;
  revision: Revision4;
  role: AuthoredField;
  stack: AuthoredField;
  subprojectIds: Subprojectids;
  tasks: AuthoredField;
  visible: Visible4;
}
export interface DocumentPeriod {
  endText: AuthoredField;
  id: Id5;
  present: Present;
  startText: AuthoredField;
}
export interface LanguageRecord {
  id: Id6;
  kind: Kind5;
  legacyText: AuthoredField | null;
  name: AuthoredField;
  proficiency: AuthoredField;
  revision: Revision5;
  visible: Visible5;
}
export interface ProfileRecord {
  id: Id7;
  kind: Kind6;
  revision: Revision6;
  text: AuthoredField;
  visible: Visible6;
}
export interface SkillsFocusRecord {
  focus: Focus;
  focusFieldId: Focusfieldid;
  id: Id9;
  kind: Kind7;
  revision: Revision7;
  skillsText: AuthoredField;
  visible: Visible7;
}
export interface FocusEntry {
  catalogId: Catalogid;
  display: AuthoredField;
  factIds: Factids1;
  id: Id8;
}
export interface Job {
  employer: Employer;
  factIds: Factids2;
  id: Id10;
  periods: Periods1;
  role: Role;
  subprojects: Subprojects;
}
export interface Period {
  end: PartialDate | null;
  start: PartialDate;
}
export interface Subproject {
  factIds: Factids3;
  id: Id11;
  name: Name;
  period: Period | null;
}
export interface GuiTextFact {
  evidence: Evidence2;
  id: Id12;
  importance: Importance;
  jobId: Jobid;
  kind: Kind8;
  literalEvidence: Literalevidence;
  origin: Origin1;
  revision: Revision8;
  subprojectId: Subprojectid;
  value: TextValue;
}
export interface EvidenceSpan {
  sourceId: Sourceid1;
  sourceRevision: Sourcerevision1;
  text: Text1;
  unitId: Unitid1;
  unitRevision: Unitrevision1;
}
export interface TextValue {
  text: Text2;
}
export interface GuiTechnologyFact {
  evidence: Evidence3;
  id: Id13;
  importance: Importance1;
  jobId: Jobid1;
  kind: Kind9;
  literalEvidence: Literalevidence1;
  origin: Origin2;
  revision: Revision9;
  subprojectId: Subprojectid1;
  value: TechnologyValue;
}
export interface TechnologyValue {
  canonicalId: Canonicalid;
  display: Display;
  scope: Scope;
}
export interface GuiMetricFact {
  evidence: Evidence4;
  id: Id14;
  importance: Importance2;
  jobId: Jobid2;
  kind: Kind10;
  literalEvidence: Literalevidence2;
  origin: Origin3;
  revision: Revision10;
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
export interface GuiLeadershipFact {
  evidence: Evidence5;
  id: Id15;
  importance: Importance3;
  jobId: Jobid3;
  kind: Kind11;
  literalEvidence: Literalevidence3;
  origin: Origin4;
  revision: Revision11;
  subprojectId: Subprojectid3;
  value: LeadershipValue;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface GuiDateFact {
  evidence: Evidence6;
  id: Id16;
  importance: Importance4;
  jobId: Jobid4;
  kind: Kind12;
  literalEvidence: Literalevidence4;
  origin: Origin5;
  revision: Revision12;
  subprojectId: Subprojectid4;
  value: PartialDate;
}
export interface TextFact {
  evidence: Evidence7;
  id: Id17;
  importance: Importance5;
  jobId: Jobid5;
  kind: Kind13;
  origin: Origin6;
  revision: Revision13;
  subprojectId: Subprojectid5;
  value: TextValue;
}
export interface TechnologyFact {
  evidence: Evidence8;
  id: Id18;
  importance: Importance6;
  jobId: Jobid6;
  kind: Kind14;
  origin: Origin7;
  revision: Revision14;
  subprojectId: Subprojectid6;
  value: TechnologyValue;
}
export interface MetricFact {
  evidence: Evidence9;
  id: Id19;
  importance: Importance7;
  jobId: Jobid7;
  kind: Kind15;
  origin: Origin8;
  revision: Revision15;
  subprojectId: Subprojectid7;
  value: MetricValue;
}
export interface LeadershipFact {
  evidence: Evidence10;
  id: Id20;
  importance: Importance8;
  jobId: Jobid8;
  kind: Kind16;
  origin: Origin9;
  revision: Revision16;
  subprojectId: Subprojectid8;
  value: LeadershipValue;
}
export interface DateFact {
  evidence: Evidence11;
  id: Id21;
  importance: Importance9;
  jobId: Jobid9;
  kind: Kind17;
  origin: Origin10;
  revision: Revision17;
  subprojectId: Subprojectid9;
  value: PartialDate;
}
export interface CandidateFact {
  evidence: Evidence12;
  id: Id22;
  importance: Importance10;
  jobId: Jobid10;
  kind: Kind18;
  origin: Origin11;
  revision: Revision18;
  subprojectId: Subprojectid10;
  value: CandidateDetail;
}
export interface CandidateDetail {
  field: Field;
  fieldId?: Fieldid1;
  text: Text3;
}
export interface NameAssessmentFact {
  evidence: Evidence13;
  id: Id23;
  importance: Importance11;
  jobId: Jobid11;
  kind: Kind19;
  origin: Origin12;
  revision: Revision19;
  subprojectId: Subprojectid11;
  value: NameAssessment;
}
export interface NameAssessment {
  evidence: Evidence14;
  missingSurname: Missingsurname;
  revision: Revision20;
}
export interface ObservationFact {
  evidence: Evidence15;
  id: Id24;
  importance: Importance12;
  jobId: Jobid12;
  kind: Kind20;
  origin: Origin13;
  revision: Revision21;
  subprojectId: Subprojectid12;
  value: ObservationAssessment;
}
export interface ObservationAssessment {
  evidence: EvidenceSpan | null;
  revision: Revision22;
  sourceObservedAt: PartialDate | null;
}
export interface EmploymentFact {
  evidence: Evidence16;
  id: Id25;
  importance: Importance13;
  jobId: Jobid13;
  kind: Kind21;
  literalEvidence: Literalevidence5;
  origin: Origin14;
  revision: Revision23;
  subprojectId: Subprojectid13;
  value: EmploymentValue;
}
export interface EmploymentValue {
  employer: Employer1;
  jobId: Jobid14;
  periods: Periods2;
  role: Role1;
  subprojects: Subprojects1;
}
export interface EmploymentPeriodValue {
  end: PartialDate | null;
  endText: Endtext;
  evidence: Evidence17;
  id: Id26;
  present: Present1;
  start: PartialDate | null;
  startText: Starttext;
}
export interface GuiOperation {
  analysisBatch?: AnalysisBatch | null;
  baseRevision: Baserevision;
  capturedDocumentRevision: Captureddocumentrevision;
  dependencies: Dependencies | null;
  docxError?: DocxError | null;
  editorialRecommendations?: Editorialrecommendations;
  errorCode: Errorcode;
  events: Events;
  id: Id27;
  kind: Kind25;
  projectId: Projectid;
  renderSnapshotId?: Rendersnapshotid;
  resultFingerprint: Resultfingerprint;
  rulesUsed: Rules | null;
  status: Status;
  targetFieldIds: Targetfieldids;
  usage: Usage | null;
}
export interface AnalysisBatch {
  completedFieldIds: Completedfieldids;
  enabled: Enabled;
  phase: Phase;
}
export interface Dependencies {
  dependencyFingerprint: Dependencyfingerprint;
  documentRevision: Documentrevision;
  projectRevision: Projectrevision;
  rulesSha256: Rulessha256;
  sourceFingerprint: Sourcefingerprint;
}
export interface DocxError {
  anchor: Anchor;
  code: Code;
  path: Path;
}
export interface FieldAnchor {
  fieldId: Fieldid2;
  kind: Kind22;
  range: Range | null;
}
export interface Range {
  end: End;
  start: Start;
}
export interface SectionAnchor {
  kind: Kind23;
  sectionId: Sectionid;
}
export interface DocumentAnchor {
  kind: Kind24;
}
export interface GuiOperationEvent {
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
export interface Rules {
  markdown: Markdown;
  revision: Revision24;
  sha256: Sha256;
}
export interface Proposal {
  baseBlockRevision: Baseblockrevision;
  blockId: Blockid;
  dependencyHash: Dependencyhash;
  evidenceFactIds: Evidencefactids;
  findings: Findings;
  id: Id28;
  kind: Kind26;
  operationId: Operationid;
  replacementText: Replacementtext;
}
export interface RenderSnapshotV4 {
  artifactAvailable: Artifactavailable;
  documentRevision: Documentrevision1;
  docx: AssetRef;
  id: Id29;
  pdf: Pdf;
  projectRevision: Projectrevision1;
  renderInputFingerprint: Renderinputfingerprint;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  templateId: Templateid;
  templateSha256: Templatesha256;
  templateVersion: Templateversion;
}
export interface AssetRef {
  path: Path1;
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
  id: Id30;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision27;
  units: Units;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id31;
  origin: Origin15;
  revision: Revision26;
  text: Text4;
  unitId: Unitid2;
}
export interface SourceUnit {
  disposition: Disposition1;
  id: Id32;
  location: SourceLocation;
  order: Order;
  representedFactIds: Representedfactids;
  revision: Revision28;
  text: Text5;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind27;
  row: Row;
}
export interface TemplateManifest {
  assets: Assets;
  contentPolicyVersion: Contentpolicyversion;
  id: Id33;
  packageSha256: Packagesha256;
  version: Version;
}
export interface Block {
  contentPolicyVersion: Contentpolicyversion1;
  dependencyHash: Dependencyhash1;
  id: Id34;
  kind: Kind28;
  previous: BlockState | null;
  revision: Revision29;
  state: BlockState;
  status: Status1;
  visible: Visible8;
}
export interface BlockState {
  factIds: Factids4;
  factRevisions: Factrevisions;
  locked: Locked;
  origin: Origin16;
  text: Text6;
}
export interface Factrevisions {
  [k: string]: number;
}
