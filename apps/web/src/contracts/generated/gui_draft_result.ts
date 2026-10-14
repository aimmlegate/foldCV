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
export type Sourceid1 = string;
export type Sourcerevision1 = number;
export type Unitid1 = string;
export type Unitrevision1 = number;
export type Evidence1 = Evidence2[];
export type Factids1 = string[];
export type Fieldid1 = string;
export type Origin = "source" | "generated" | "user" | "migration";
export type Text1 = string;
/**
 * @maxItems 100
 */
export type Details = AuthoredField[];
export type Id1 = "candidate";
export type Kind3 = "candidate";
export type Revision = number;
export type Visible = true;
export type Id2 = string;
export type Kind4 = "certification";
export type Revision1 = number;
export type Visible1 = boolean;
export type Certifications = CertificationRecord[];
export type Id3 = "early-career";
export type Kind5 = "early-career";
export type Representedjobids = string[];
export type Revision2 = number;
export type Visible2 = boolean;
export type Id4 = string;
export type Kind6 = "education";
export type Revision3 = number;
export type Visible3 = boolean;
export type Education = EducationRecord[];
export type Id5 = string;
export type Kind7 = "job";
export type Id6 = string;
export type Present = boolean;
export type Periods = DocumentPeriod[];
export type Periodsfieldid = string;
export type Revision4 = number;
export type Subprojectids = string[];
export type Visible4 = boolean;
export type Jobs = JobRecord[];
export type Id7 = string;
export type Kind8 = "language";
export type Revision5 = number;
export type Visible5 = boolean;
export type Languages = LanguageRecord[];
export type Id8 = "profile";
export type Kind9 = "profile";
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
export type Catalogid1 = string;
export type Factids2 = string[];
export type Id9 = string;
export type Focusfieldid = string;
export type Id10 = "skills-focus";
export type Kind10 = "skills-focus";
export type Revision7 = number;
export type Visible7 = boolean;
export type Factids3 = string[];
export type Catalogid2 = string;
export type Display = string;
export type Factids4 = string[];
export type Focus1 = PlanFocus[];
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Disposition = "detailed" | "early-career";
export type Factids5 = string[];
export type Jobid = string;
export type Jobs1 = JobDisposition[];
export type Origin1 = "model" | "migration";
export type Profilelanguage = ("ru" | "en") | null;
export type Revision8 = number;
export type Rulesrevision = number | null;
export type Sourcelanguage = "ru" | "en" | "mixed";
export type Factids6 = string[];
export type Title = string;
export type Technologygroups = TechnologyGroup[];

export interface GuiDraftResult {
  annotations: Annotations;
  document: Document;
  editorialPlan: EditorialPlan;
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
  details?: Details;
  id: Id1;
  kind: Kind3;
  location: AuthoredField;
  name: AuthoredField;
  revision: Revision;
  title: AuthoredField;
  visible: Visible;
}
export interface AuthoredField {
  evidence: Evidence1;
  factIds: Factids1;
  fieldId: Fieldid1;
  origin: Origin;
  text: Text1;
}
export interface Evidence2 {
  sourceId: Sourceid1;
  sourceRevision: Sourcerevision1;
  unitId: Unitid1;
  unitRevision: Unitrevision1;
}
export interface CertificationRecord {
  dateText: AuthoredField;
  id: Id2;
  issuer: AuthoredField;
  kind: Kind4;
  legacyText: AuthoredField | null;
  name: AuthoredField;
  revision: Revision1;
  visible: Visible1;
}
export interface EarlyCareerRecord {
  id: Id3;
  kind: Kind5;
  representedJobIds: Representedjobids;
  revision: Revision2;
  text: AuthoredField;
  visible: Visible2;
}
export interface EducationRecord {
  dateText: AuthoredField;
  id: Id4;
  institution: AuthoredField;
  kind: Kind6;
  legacyText: AuthoredField | null;
  qualification: AuthoredField;
  revision: Revision3;
  specialty: AuthoredField;
  visible: Visible3;
}
export interface JobRecord {
  context: AuthoredField;
  employer: AuthoredField;
  id: Id5;
  kind: Kind7;
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
  id: Id6;
  present: Present;
  startText: AuthoredField;
}
export interface LanguageRecord {
  id: Id7;
  kind: Kind8;
  legacyText: AuthoredField | null;
  name: AuthoredField;
  proficiency: AuthoredField;
  revision: Revision5;
  visible: Visible5;
}
export interface ProfileRecord {
  id: Id8;
  kind: Kind9;
  revision: Revision6;
  text: AuthoredField;
  visible: Visible6;
}
export interface SkillsFocusRecord {
  focus: Focus;
  focusFieldId: Focusfieldid;
  id: Id10;
  kind: Kind10;
  revision: Revision7;
  skillsText: AuthoredField;
  visible: Visible7;
}
export interface FocusEntry {
  catalogId: Catalogid1;
  display: AuthoredField;
  factIds: Factids2;
  id: Id9;
}
export interface EditorialPlan {
  factIds: Factids3;
  focus: Focus1;
  formattingAsOf: PartialDate;
  jobs: Jobs1;
  origin: Origin1;
  profileLanguage: Profilelanguage;
  revision: Revision8;
  rulesRevision: Rulesrevision;
  sourceLanguage: Sourcelanguage;
  technologyGroups: Technologygroups;
}
export interface PlanFocus {
  catalogId: Catalogid2;
  display: Display;
  factIds: Factids4;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface JobDisposition {
  disposition: Disposition;
  factIds: Factids5;
  jobId: Jobid;
}
export interface TechnologyGroup {
  factIds: Factids6;
  title: Title;
}
