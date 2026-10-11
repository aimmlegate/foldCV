export type Anchor = FieldAnchor | SectionAnchor | DocumentAnchor;
export type Fieldid = string;
export type Kind = "field";
export type End = number;
export type Start = number;
export type Kind1 = "section";
export type Sectionid = string;
export type Kind2 = "document";
export type Code = string;
export type Dependencyfingerprint = string;
export type Documentrevision = number;
export type Projectrevision = number;
export type Rulessha256 = string | null;
export type Sourcefingerprint = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Text = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Factids = string[];
export type Id = string;
export type Reason = string;
export type Catalogid = string;
export type Reason1 = "duplicate" | "unknown-ID" | "missing-logo" | "capacity";
export type Removedfocus = FocusRemoval[];
export type Resolved = boolean;
export type Type = "missing" | "conflicting" | "stale" | "warning";
export type Updatesuggestionid = string | null;
export type Annotations = Annotation[];
export type Createdat = string;
export type Documentrevision1 = number;
export type Canonicalaliases = string[];
export type Completeexposure = boolean;
export type Dependencyfingerprint1 = string;
export type Display = string | null;
export type Fieldid1 = string;
export type Monthsmax = number | null;
export type Monthsmin = number | null;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Valid = boolean;
export type Values = DerivedValue[];
export type Documentrevision2 = number;
export type Annotations1 = Annotation[];
export type Documentrevision3 = number;
export type Authoritativerevision = number;
export type Factid = string;
export type Origin = "source" | "user" | "model" | "migration";
export type Ownerslotid = string;
export type Revision = number;
export type Factstamps = FactStamp[];
export type Sourceid1 = string;
export type Sourcerevision1 = number;
export type Unitid1 = string;
export type Unitrevision1 = number;
export type Evidence1 = Evidence2[];
export type Id1 = string;
export type Importance = "essential" | "normal" | "minor";
export type Jobid = string | null;
export type Kind3 = "text";
export type Origin1 = "source" | "user";
export type Revision1 = number;
export type Subprojectid = string | null;
export type Text1 = string;
export type Evidence3 = Evidence2[];
export type Id2 = string;
export type Importance1 = "essential" | "normal" | "minor";
export type Jobid1 = string | null;
export type Kind4 = "technology";
export type Origin2 = "source" | "user";
export type Revision2 = number;
export type Subprojectid1 = string | null;
export type Canonicalid = string;
export type Display1 = string;
export type Scope = "global" | "job" | "subproject";
export type Evidence4 = Evidence2[];
export type Id3 = string;
export type Importance2 = "essential" | "normal" | "minor";
export type Jobid2 = string | null;
export type Kind5 = "metric";
export type Origin3 = "source" | "user";
export type Revision3 = number;
export type Subprojectid2 = string | null;
export type Attribution = "personal" | "team" | "organization" | "unknown";
export type Baseline = string | null;
export type Comparator = "exact" | "at_least" | "at_most" | "approximately" | "range";
export type Number = number;
export type Period = string | null;
export type Qualifiers = string[];
export type Result = string | null;
export type Scope1 = string | null;
export type Unit = string;
export type Uppernumber = number | null;
export type Evidence5 = Evidence2[];
export type Id4 = string;
export type Importance3 = "essential" | "normal" | "minor";
export type Jobid3 = string | null;
export type Kind6 = "leadership";
export type Origin4 = "source" | "user";
export type Revision4 = number;
export type Subprojectid3 = string | null;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Evidence6 = Evidence2[];
export type Id5 = string;
export type Importance4 = "essential" | "normal" | "minor";
export type Jobid4 = string | null;
export type Kind7 = "date";
export type Origin5 = "source" | "user";
export type Revision5 = number;
export type Subprojectid4 = string | null;
export type Evidence7 = Evidence2[];
export type Id6 = string;
export type Importance5 = "essential" | "normal" | "minor";
export type Jobid5 = string | null;
export type Kind8 = "candidate_detail";
export type Origin6 = "source" | "user";
export type Revision6 = number;
export type Subprojectid5 = string | null;
export type Field = "name" | "title" | "location" | "education" | "certification" | "language" | "private_metadata";
export type Text2 = string;
export type Evidence8 = Evidence2[];
export type Id7 = string;
export type Importance6 = "essential" | "normal" | "minor";
export type Jobid6 = string | null;
export type Kind9 = "name_assessment";
export type Origin7 = "source" | "user";
export type Revision7 = number;
export type Subprojectid6 = string | null;
export type Evidence9 = EvidenceSpan[];
export type Missingsurname = boolean | null;
export type Revision8 = number;
export type Evidence10 = Evidence2[];
export type Id8 = string;
export type Importance7 = "essential" | "normal" | "minor";
export type Jobid7 = string | null;
export type Kind10 = "source_observation";
export type Origin8 = "source" | "user";
export type Revision9 = number;
export type Subprojectid7 = string | null;
export type Revision10 = number;
export type Facts = (
  | (TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact)
  | CandidateFact
  | NameAssessmentFact
  | ObservationFact
)[];
export type Projectrevision1 = number;
export type Record =
  | CandidateRecord
  | ProfileRecord
  | JobRecord
  | EducationRecord
  | CertificationRecord
  | LanguageRecord
  | SkillsFocusRecord
  | EarlyCareerRecord;
export type Id9 = "candidate";
export type Kind11 = "candidate";
export type Evidence11 = Evidence2[];
export type Factids1 = string[];
export type Fieldid2 = string;
export type Origin9 = "source" | "generated" | "user" | "migration";
export type Text3 = string;
export type Revision11 = number;
export type Visible = true;
export type Id10 = "profile";
export type Kind12 = "profile";
export type Revision12 = number;
export type Visible1 = boolean;
export type Id11 = string;
export type Kind13 = "job";
export type Id12 = string;
export type Present = boolean;
export type Periods = DocumentPeriod[];
export type Periodsfieldid = string;
export type Revision13 = number;
export type Subprojectids = string[];
export type Visible2 = boolean;
export type Id13 = string;
export type Kind14 = "education";
export type Revision14 = number;
export type Visible3 = boolean;
export type Id14 = string;
export type Kind15 = "certification";
export type Revision15 = number;
export type Visible4 = boolean;
export type Id15 = string;
export type Kind16 = "language";
export type Revision16 = number;
export type Visible5 = boolean;
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
export type Catalogid1 = string;
export type Factids2 = string[];
export type Id16 = string;
export type Focusfieldid = string;
export type Id17 = "skills-focus";
export type Kind17 = "skills-focus";
export type Revision17 = number;
export type Visible6 = boolean;
export type Id18 = "early-career";
export type Kind18 = "early-career";
export type Representedjobids = string[];
export type Revision18 = number;
export type Visible7 = boolean;
export type Fieldid3 = string;
export type Text4 = string;
export type Bufferedfields = BufferedField[];
export type Sessionid = string;
export type Starteddocumentrevision = number;
export type Factids3 = string[];
export type Catalogid2 = string;
export type Display2 = string;
export type Factids4 = string[];
export type Focus1 = PlanFocus[];
export type Disposition = "detailed" | "early-career";
export type Factids5 = string[];
export type Jobid8 = string;
export type Jobs = JobDisposition[];
export type Origin10 = "model" | "migration";
export type Profilelanguage = ("ru" | "en") | null;
export type Revision19 = number;
export type Rulesrevision = number | null;
export type Sourcelanguage = "ru" | "en" | "mixed";
export type Factids6 = string[];
export type Title = string;
export type Technologygroups = TechnologyGroup[];
export type Id19 = string;
export type Projectid = string;
export type Markdown = string;
export type Revision20 = number;
export type Sha256 = string;
export type Sourceids = string[];
export type Dependencyfingerprint2 = string;
export type Anchor1 = FieldAnchor | SectionAnchor | DocumentAnchor;
export type Code1 =
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
export type Errorcode = string | null;
export type Kind19 = "extract" | "normalize_semantics" | "draft_prose" | "assemble" | "render";
export type Operationid = string | null;
export type Resultfingerprint = string | null;
export type Status = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Stages = GenerationStage[];
export type Status1 = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Generations = Generation[];
export type Contentpolicyversion = string;
export type Dependencyhash = string;
export type Id20 = string;
export type Kind20 = "profile" | "job_prose" | "contact" | "focus" | "education" | "skills" | "early_career";
export type Factids7 = string[];
export type Locked = boolean;
export type Origin11 = "source" | "generated" | "manual";
export type Text5 = string;
export type Revision21 = number;
export type Status2 = "empty" | "running" | "proposed" | "ready" | "stale" | "error";
export type Visible8 = boolean;
export type Blocks = Block[];
export type Baseblockrevision = number;
export type Blockid = string;
export type Dependencyhash1 = string;
export type Evidencefactids = string[];
export type Findings = string[];
export type Id21 = string;
export type Kind21 = "draft_prose" | "rewrite_prose";
export type Operationid1 = string;
export type Replacementtext = string;
export type Proposals = Proposal[];
export type Artifactavailable = boolean;
export type Blockid1 = string;
export type Blockrevision = number;
export type Text6 = string;
export type Blocks1 = RenderBlock[];
export type Path1 = string;
export type Sha2561 = string;
export type Size = number;
export type Id22 = string;
export type Projectrevision2 = number;
export type Rendererversion = string;
export type Snapshotsha256 = string;
export type Templateid = string;
export type Templateversion = string;
export type Renders = LegacyRender[];
export type Issueid = string;
export type Targetid = string;
export type Targetkind = "fact" | "block";
export type Targetrevision = number;
export type Acknowledgments = Acknowledgment[];
export type Disposition1 = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "excluded";
export type Reason2 = string | null;
export type Targetid1 = string;
export type Targetkind1 = "source_unit" | "fact" | "block";
export type Targetrevision1 = number;
export type Decisions = ReviewDecision[];
export type Evidence12 = Evidence2[];
export type Factids8 = string[];
export type Id23 = string;
export type Label = string;
export type Originalkind = string;
export type Text7 = string;
export type Visible9 = boolean;
export type Unmappedtext = LegacyText[];
export type Migrationnotices = string[];
export type Clientmutationid = string;
export type Documentrevision4 = number;
export type Payloadsha256 = string;
export type Projectrevision3 = number;
export type Rejectionreason = string | null;
export type Status3 = "applied" | "stale" | "rejected";
export type Mutationreplay = MutationReplay[];
export type Extractedtext = string;
export type Extractionfingerprint = string | null;
export type Facts1 = (
  | (TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact)
  | CandidateFact
  | NameAssessmentFact
  | ObservationFact
)[];
export type Baserevision = number;
export type Captureddocumentrevision = number | null;
export type Errorcode1 = string | null;
export type Requestid = string;
export type Sequence = number;
export type Stage = string | null;
export type Type1 =
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
export type Id24 = string;
export type Kind22 =
  | "extract"
  | "validate"
  | "render"
  | "project_save"
  | "normalize_semantics"
  | "draft_prose"
  | "rewrite_prose"
  | "reconcile_edits";
export type Projectid1 = string;
export type Resultfingerprint1 = string | null;
export type Status4 = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Targetfieldids = string[];
export type Operations = GuiOperation[];
export type Artifactavailable1 = boolean;
export type Documentrevision5 = number;
export type Id25 = string;
export type Pdf = null;
export type Projectrevision4 = number;
export type Renderinputfingerprint = string;
export type Renderersha256 = string;
export type Rendererversion1 = string;
export type Templateid1 = string;
export type Templatesha256 = string;
export type Templateversion1 = string;
export type Renders1 = RenderSnapshotV4[];
export type Selectedinput = "text" | "file";
export type Selectedsourceid = string | null;
export type Byteref = string;
export type Bytesha256 = string;
export type Id26 = string;
export type Mimetype = string;
export type Originalname = string;
export type Id27 = string;
export type Origin12 = "user";
export type Revision22 = number;
export type Text8 = string;
export type Unitid2 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision23 = number;
export type Disposition2 = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id28 = string;
export type Column = number | null;
export type Index = number;
export type Kind23 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order = number;
export type Representedfactids = string[];
export type Revision24 = number;
export type Text9 = string;
export type Units = SourceUnit[];
export type Warnings = string[];
export type Sources = Source[];
export type Warnings1 = string[];
export type Createdat1 = string;
export type Certifications = CertificationRecord[];
export type Education = EducationRecord[];
export type Jobs1 = JobRecord[];
export type Languages = LanguageRecord[];
export type Employer = string;
export type Factids9 = string[];
export type Id29 = string;
export type Periods1 = Period1[];
export type Role = string;
export type Factids10 = string[];
export type Id30 = string;
export type Name = string;
export type Subprojects = Subproject[];
export type Employment = Job[];
export type Facts2 = (
  | (TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact)
  | CandidateFact
  | NameAssessmentFact
  | ObservationFact
)[];
export type Operations1 = GuiOperation[];
export type Projectid2 = string;
export type Proposals1 = Proposal[];
export type Renders2 = RenderSnapshotV4[];
export type Revision25 = number;
export type Schemaversion = 4;
export type Sources1 = Source[];
export type Assets = AssetRef[];
export type Contentpolicyversion1 = string;
export type Id31 = string;
export type Packagesha256 = string;
export type Version = string;
export type Views = Block[];
export type Projectid3 = string;
export type Projectrevision5 = number;
export type Factids11 = string[];
export type Id32 = string;
export type Reason3 = string;
export type Fieldid4 = string;
export type Text10 = string;
export type Replacements = FieldReplacement[];
export type Relatedupdatesuggestions = RelatedUpdateSuggestion[];
export type Schemaversion1 = 5;
export type Factids12 = string[];
export type Id33 = string;
export type Reason4 = "hidden" | "deleted";
export type Recordid = string;
export type Revision26 = number;
export type Sourceids1 = string[];
export type Sourceexclusions = SourceExclusion[];
export type Title1 = string;
export type Titlemanuallyset = boolean;
export type Updatedat = string;

export interface WorkspaceV5 {
  annotations: Annotations;
  createdAt: Createdat;
  derivedState: DerivedState | null;
  documentRevision: Documentrevision2;
  editSessions: Editsessions;
  editorialPlan: EditorialPlan | null;
  formattingAsOf: PartialDate;
  generations: Generations;
  legacyData: LegacyData | null;
  migrationNotices: Migrationnotices;
  mutationReplay: Mutationreplay;
  preDraft: PreDraft | null;
  project: ProjectV4 | null;
  projectId: Projectid3;
  projectRevision: Projectrevision5;
  relatedUpdateSuggestions: Relatedupdatesuggestions;
  rulesUsed: Rules | null;
  schemaVersion: Schemaversion1;
  sourceExclusions: Sourceexclusions;
  sourceObservedAt: PartialDate | null;
  title: Title1;
  titleManuallySet: Titlemanuallyset;
  undoSlots: Undoslots;
  updatedAt: Updatedat;
}
export interface Annotation {
  anchor: Anchor;
  code: Code;
  dependencies: Dependencies;
  evidence: Evidence;
  factIds: Factids;
  id: Id;
  reason: Reason;
  removedFocus: Removedfocus;
  resolved: Resolved;
  type: Type;
  updateSuggestionId: Updatesuggestionid;
}
export interface FieldAnchor {
  fieldId: Fieldid;
  kind: Kind;
  range: Range | null;
}
export interface Range {
  end: End;
  start: Start;
}
export interface SectionAnchor {
  kind: Kind1;
  sectionId: Sectionid;
}
export interface DocumentAnchor {
  kind: Kind2;
}
export interface Dependencies {
  dependencyFingerprint: Dependencyfingerprint;
  documentRevision: Documentrevision;
  projectRevision: Projectrevision;
  rulesSha256: Rulessha256;
  sourceFingerprint: Sourcefingerprint;
}
export interface EvidenceSpan {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  text: Text;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface FocusRemoval {
  catalogId: Catalogid;
  reason: Reason1;
}
export interface DerivedState {
  documentRevision: Documentrevision1;
  values: Values;
}
export interface DerivedValue {
  canonicalAliases: Canonicalaliases;
  completeExposure: Completeexposure;
  dependencyFingerprint: Dependencyfingerprint1;
  display: Display;
  fieldId: Fieldid1;
  monthsMax: Monthsmax;
  monthsMin: Monthsmin;
  parsedDate: PartialDate | null;
  valid: Valid;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface Editsessions {
  [k: string]: EditSession;
}
export interface EditSession {
  baseline: BlockCheckpoint;
  bufferedFields: Bufferedfields;
  sessionId: Sessionid;
  startedDocumentRevision: Starteddocumentrevision;
}
export interface BlockCheckpoint {
  annotations: Annotations1;
  documentRevision: Documentrevision3;
  factStamps: Factstamps;
  facts: Facts;
  projectRevision: Projectrevision1;
  record: Record;
}
export interface FactStamp {
  authoritativeRevision: Authoritativerevision;
  factId: Factid;
  origin: Origin;
  ownerSlotId: Ownerslotid;
  revision: Revision;
}
export interface TextFact {
  evidence: Evidence1;
  id: Id1;
  importance: Importance;
  jobId: Jobid;
  kind: Kind3;
  origin: Origin1;
  revision: Revision1;
  subprojectId: Subprojectid;
  value: TextValue;
}
export interface Evidence2 {
  sourceId: Sourceid1;
  sourceRevision: Sourcerevision1;
  unitId: Unitid1;
  unitRevision: Unitrevision1;
}
export interface TextValue {
  text: Text1;
}
export interface TechnologyFact {
  evidence: Evidence3;
  id: Id2;
  importance: Importance1;
  jobId: Jobid1;
  kind: Kind4;
  origin: Origin2;
  revision: Revision2;
  subprojectId: Subprojectid1;
  value: TechnologyValue;
}
export interface TechnologyValue {
  canonicalId: Canonicalid;
  display: Display1;
  scope: Scope;
}
export interface MetricFact {
  evidence: Evidence4;
  id: Id3;
  importance: Importance2;
  jobId: Jobid2;
  kind: Kind5;
  origin: Origin3;
  revision: Revision3;
  subprojectId: Subprojectid2;
  value: MetricValue;
}
export interface MetricValue {
  attribution: Attribution;
  baseline: Baseline;
  comparator: Comparator;
  number: Number;
  period: Period;
  qualifiers: Qualifiers;
  result: Result;
  scope: Scope1;
  unit: Unit;
  upperNumber: Uppernumber;
}
export interface LeadershipFact {
  evidence: Evidence5;
  id: Id4;
  importance: Importance3;
  jobId: Jobid3;
  kind: Kind6;
  origin: Origin4;
  revision: Revision4;
  subprojectId: Subprojectid3;
  value: LeadershipValue;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface DateFact {
  evidence: Evidence6;
  id: Id5;
  importance: Importance4;
  jobId: Jobid4;
  kind: Kind7;
  origin: Origin5;
  revision: Revision5;
  subprojectId: Subprojectid4;
  value: PartialDate;
}
export interface CandidateFact {
  evidence: Evidence7;
  id: Id6;
  importance: Importance5;
  jobId: Jobid5;
  kind: Kind8;
  origin: Origin6;
  revision: Revision6;
  subprojectId: Subprojectid5;
  value: CandidateDetail;
}
export interface CandidateDetail {
  field: Field;
  text: Text2;
}
export interface NameAssessmentFact {
  evidence: Evidence8;
  id: Id7;
  importance: Importance6;
  jobId: Jobid6;
  kind: Kind9;
  origin: Origin7;
  revision: Revision7;
  subprojectId: Subprojectid6;
  value: NameAssessment;
}
export interface NameAssessment {
  evidence: Evidence9;
  missingSurname: Missingsurname;
  revision: Revision8;
}
export interface ObservationFact {
  evidence: Evidence10;
  id: Id8;
  importance: Importance7;
  jobId: Jobid7;
  kind: Kind10;
  origin: Origin8;
  revision: Revision9;
  subprojectId: Subprojectid7;
  value: ObservationAssessment;
}
export interface ObservationAssessment {
  evidence: EvidenceSpan | null;
  revision: Revision10;
  sourceObservedAt: PartialDate | null;
}
export interface CandidateRecord {
  id: Id9;
  kind: Kind11;
  location: AuthoredField;
  name: AuthoredField;
  revision: Revision11;
  title: AuthoredField;
  visible: Visible;
}
export interface AuthoredField {
  evidence: Evidence11;
  factIds: Factids1;
  fieldId: Fieldid2;
  origin: Origin9;
  text: Text3;
}
export interface ProfileRecord {
  id: Id10;
  kind: Kind12;
  revision: Revision12;
  text: AuthoredField;
  visible: Visible1;
}
export interface JobRecord {
  context: AuthoredField;
  employer: AuthoredField;
  id: Id11;
  kind: Kind13;
  periods: Periods;
  periodsFieldId: Periodsfieldid;
  results: AuthoredField;
  revision: Revision13;
  role: AuthoredField;
  stack: AuthoredField;
  subprojectIds: Subprojectids;
  tasks: AuthoredField;
  visible: Visible2;
}
export interface DocumentPeriod {
  endText: AuthoredField;
  id: Id12;
  present: Present;
  startText: AuthoredField;
}
export interface EducationRecord {
  dateText: AuthoredField;
  id: Id13;
  institution: AuthoredField;
  kind: Kind14;
  legacyText: AuthoredField | null;
  qualification: AuthoredField;
  revision: Revision14;
  specialty: AuthoredField;
  visible: Visible3;
}
export interface CertificationRecord {
  dateText: AuthoredField;
  id: Id14;
  issuer: AuthoredField;
  kind: Kind15;
  legacyText: AuthoredField | null;
  name: AuthoredField;
  revision: Revision15;
  visible: Visible4;
}
export interface LanguageRecord {
  id: Id15;
  kind: Kind16;
  legacyText: AuthoredField | null;
  name: AuthoredField;
  proficiency: AuthoredField;
  revision: Revision16;
  visible: Visible5;
}
export interface SkillsFocusRecord {
  focus: Focus;
  focusFieldId: Focusfieldid;
  id: Id17;
  kind: Kind17;
  revision: Revision17;
  skillsText: AuthoredField;
  visible: Visible6;
}
export interface FocusEntry {
  catalogId: Catalogid1;
  display: AuthoredField;
  factIds: Factids2;
  id: Id16;
}
export interface EarlyCareerRecord {
  id: Id18;
  kind: Kind18;
  representedJobIds: Representedjobids;
  revision: Revision18;
  text: AuthoredField;
  visible: Visible7;
}
export interface BufferedField {
  fieldId: Fieldid3;
  text: Text4;
}
export interface EditorialPlan {
  factIds: Factids3;
  focus: Focus1;
  formattingAsOf: PartialDate;
  jobs: Jobs;
  origin: Origin10;
  profileLanguage: Profilelanguage;
  revision: Revision19;
  rulesRevision: Rulesrevision;
  sourceLanguage: Sourcelanguage;
  technologyGroups: Technologygroups;
}
export interface PlanFocus {
  catalogId: Catalogid2;
  display: Display2;
  factIds: Factids4;
}
export interface JobDisposition {
  disposition: Disposition;
  factIds: Factids5;
  jobId: Jobid8;
}
export interface TechnologyGroup {
  factIds: Factids6;
  title: Title;
}
export interface Generation {
  dependencies: Dependencies;
  formattingAsOf: PartialDate;
  id: Id19;
  projectId: Projectid;
  rulesUsed: Rules;
  sourceIds: Sourceids;
  stages: Stages;
  status: Status1;
}
export interface Rules {
  markdown: Markdown;
  revision: Revision20;
  sha256: Sha256;
}
export interface GenerationStage {
  dependencyFingerprint: Dependencyfingerprint2;
  docxError: DocxError | null;
  errorCode: Errorcode;
  kind: Kind19;
  operationId: Operationid;
  resultFingerprint: Resultfingerprint;
  status: Status;
}
export interface DocxError {
  anchor: Anchor1;
  code: Code1;
  path: Path;
}
export interface LegacyData {
  blocks: Blocks;
  proposals: Proposals;
  renders: Renders;
  review: Review | null;
  unmappedText: Unmappedtext;
}
export interface Block {
  contentPolicyVersion: Contentpolicyversion;
  dependencyHash: Dependencyhash;
  id: Id20;
  kind: Kind20;
  previous: BlockState | null;
  revision: Revision21;
  state: BlockState;
  status: Status2;
  visible: Visible8;
}
export interface BlockState {
  factIds: Factids7;
  factRevisions: Factrevisions;
  locked: Locked;
  origin: Origin11;
  text: Text5;
}
export interface Factrevisions {
  [k: string]: number;
}
export interface Proposal {
  baseBlockRevision: Baseblockrevision;
  blockId: Blockid;
  dependencyHash: Dependencyhash1;
  evidenceFactIds: Evidencefactids;
  findings: Findings;
  id: Id21;
  kind: Kind21;
  operationId: Operationid1;
  replacementText: Replacementtext;
}
export interface LegacyRender {
  artifactAvailable: Artifactavailable;
  record: RenderSnapshot;
}
export interface RenderSnapshot {
  blocks: Blocks1;
  docx: AssetRef | null;
  id: Id22;
  pdf: AssetRef | null;
  projectRevision: Projectrevision2;
  rendererVersion: Rendererversion;
  snapshotSha256: Snapshotsha256;
  templateId: Templateid;
  templateVersion: Templateversion;
}
export interface RenderBlock {
  blockId: Blockid1;
  blockRevision: Blockrevision;
  text: Text6;
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
  disposition: Disposition1;
  reason: Reason2;
  targetId: Targetid1;
  targetKind: Targetkind1;
  targetRevision: Targetrevision1;
}
export interface LegacyText {
  evidence: Evidence12;
  factIds: Factids8;
  id: Id23;
  label: Label;
  originalKind: Originalkind;
  text: Text7;
  visible: Visible9;
}
export interface MutationReplay {
  clientMutationId: Clientmutationid;
  documentRevision: Documentrevision4;
  payloadSha256: Payloadsha256;
  projectRevision: Projectrevision3;
  rejectionReason: Rejectionreason;
  status: Status3;
}
export interface PreDraft {
  extractedText: Extractedtext;
  extractionFingerprint: Extractionfingerprint;
  facts: Facts1;
  operations: Operations;
  renders: Renders1;
  selectedInput: Selectedinput;
  selectedSourceId: Selectedsourceid;
  sources: Sources;
  warnings: Warnings1;
}
export interface GuiOperation {
  baseRevision: Baserevision;
  capturedDocumentRevision: Captureddocumentrevision;
  dependencies: Dependencies | null;
  errorCode: Errorcode1;
  events: Events;
  id: Id24;
  kind: Kind22;
  projectId: Projectid1;
  resultFingerprint: Resultfingerprint1;
  rulesUsed: Rules | null;
  status: Status4;
  targetFieldIds: Targetfieldids;
  usage: Usage | null;
}
export interface GuiOperationEvent {
  requestId: Requestid;
  sequence: Sequence;
  stage: Stage;
  type: Type1;
  usage: Usage | null;
}
export interface Usage {
  internalInferenceRequests: Internalinferencerequests;
  logicalAttempts: Logicalattempts;
  reportedInputTokens: Reportedinputtokens;
  reportedOutputTokens: Reportedoutputtokens;
}
export interface RenderSnapshotV4 {
  artifactAvailable: Artifactavailable1;
  documentRevision: Documentrevision5;
  docx: AssetRef;
  id: Id25;
  pdf: Pdf;
  projectRevision: Projectrevision4;
  renderInputFingerprint: Renderinputfingerprint;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion1;
  templateId: Templateid1;
  templateSha256: Templatesha256;
  templateVersion: Templateversion1;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id26;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision23;
  units: Units;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id27;
  origin: Origin12;
  revision: Revision22;
  text: Text8;
  unitId: Unitid2;
}
export interface SourceUnit {
  disposition: Disposition2;
  id: Id28;
  location: SourceLocation;
  order: Order;
  representedFactIds: Representedfactids;
  revision: Revision24;
  text: Text9;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind23;
  row: Row;
}
export interface ProjectV4 {
  asOf: PartialDate | null;
  createdAt: Createdat1;
  document: Document;
  employment: Employment;
  facts: Facts2;
  operations: Operations1;
  projectId: Projectid2;
  proposals: Proposals1;
  renders: Renders2;
  review: Review;
  revision: Revision25;
  schemaVersion: Schemaversion;
  sources: Sources1;
  template: TemplateManifest | null;
  views: Views;
}
export interface Document {
  candidate: CandidateRecord;
  certifications: Certifications;
  earlyCareer: EarlyCareerRecord;
  education: Education;
  jobs: Jobs1;
  languages: Languages;
  profile: ProfileRecord;
  skillsFocus: SkillsFocusRecord;
}
export interface Job {
  employer: Employer;
  factIds: Factids9;
  id: Id29;
  periods: Periods1;
  role: Role;
  subprojects: Subprojects;
}
export interface Period1 {
  end: PartialDate | null;
  start: PartialDate;
}
export interface Subproject {
  factIds: Factids10;
  id: Id30;
  name: Name;
  period: Period1 | null;
}
export interface TemplateManifest {
  assets: Assets;
  contentPolicyVersion: Contentpolicyversion1;
  id: Id31;
  packageSha256: Packagesha256;
  version: Version;
}
export interface RelatedUpdateSuggestion {
  dependencies: Dependencies;
  factIds: Factids11;
  id: Id32;
  reason: Reason3;
  replacements: Replacements;
}
export interface FieldReplacement {
  fieldId: Fieldid4;
  range: Range | null;
  text: Text10;
}
export interface SourceExclusion {
  factIds: Factids12;
  id: Id33;
  reason: Reason4;
  recordId: Recordid;
  revision: Revision26;
  sourceIds: Sourceids1;
}
export interface Undoslots {
  [k: string]: BlockCheckpoint | null;
}
