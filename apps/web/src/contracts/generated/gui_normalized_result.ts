export type Sourceid = string;
export type Sourcerevision = number;
export type Text = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Text1 = string;
export type Id = string;
export type Certifications = CertificationDetails[];
export type Id1 = string;
export type Education = EducationDetails[];
export type Sourceid1 = string;
export type Sourcerevision1 = number;
export type Unitid1 = string;
export type Unitrevision1 = number;
export type Evidence1 = Evidence2[];
export type Id2 = string;
export type Importance = "essential" | "normal" | "minor";
export type Jobid = string | null;
export type Kind = "text";
export type Origin = "source" | "user";
export type Revision = number;
export type Subprojectid = string | null;
export type Text2 = string;
export type Evidence3 = Evidence2[];
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
export type Evidence4 = Evidence2[];
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
export type Period = string | null;
export type Qualifiers = string[];
export type Result = string | null;
export type Scope1 = string | null;
export type Unit = string;
export type Uppernumber = number | null;
export type Evidence5 = Evidence2[];
export type Id5 = string;
export type Importance3 = "essential" | "normal" | "minor";
export type Jobid3 = string | null;
export type Kind3 = "leadership";
export type Origin3 = "source" | "user";
export type Revision3 = number;
export type Subprojectid3 = string | null;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Evidence6 = Evidence2[];
export type Id6 = string;
export type Importance4 = "essential" | "normal" | "minor";
export type Jobid4 = string | null;
export type Kind4 = "date";
export type Origin4 = "source" | "user";
export type Revision4 = number;
export type Subprojectid4 = string | null;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Evidence7 = Evidence2[];
export type Id7 = string;
export type Importance5 = "essential" | "normal" | "minor";
export type Jobid5 = string | null;
export type Kind5 = "candidate_detail";
export type Origin5 = "source" | "user";
export type Revision5 = number;
export type Subprojectid5 = string | null;
export type Field = "name" | "title" | "location" | "education" | "certification" | "language" | "private_metadata";
export type Text3 = string;
export type Evidence8 = Evidence2[];
export type Id8 = string;
export type Importance6 = "essential" | "normal" | "minor";
export type Jobid6 = string | null;
export type Kind6 = "name_assessment";
export type Origin6 = "source" | "user";
export type Revision6 = number;
export type Subprojectid6 = string | null;
export type Evidence9 = EvidenceSpan[];
export type Missingsurname = boolean | null;
export type Revision7 = number;
export type Evidence10 = Evidence2[];
export type Id9 = string;
export type Importance7 = "essential" | "normal" | "minor";
export type Jobid7 = string | null;
export type Kind7 = "source_observation";
export type Origin7 = "source" | "user";
export type Revision8 = number;
export type Subprojectid7 = string | null;
export type Revision9 = number;
export type Facts = (
  | (TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact)
  | CandidateFact
  | NameAssessmentFact
  | ObservationFact
)[];
export type Id10 = string;
export type Languages = LanguageDetails[];
export type Kind8 = "phone" | "email" | "messenger" | "birth_date" | "age" | "platform_metadata";
export type Privatedetails = PrivateDetails[];
export type Rulesrevision = number;
/**
 * @maxItems 40
 */
export type Certifications1 = CertificationDetails[];
/**
 * @maxItems 40
 */
export type Education1 = EducationDetails[];
export type Importance8 = "essential" | "normal" | "minor";
export type Jobtempid = string | null;
export type Kind9 = "text" | "technology" | "date" | "metric" | "leadership";
export type Sourceid2 = string;
export type Subprojecttempid = string | null;
export type Tempid = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Unitids = [string, ...string[]];
export type Value = TextValue | TechnologyValue | PartialDate | MetricValue | LeadershipValue;
/**
 * @maxItems 500
 */
export type Facts1 = ProposedFact[];
export type Employer = string;
/**
 * @maxItems 20
 */
export type Periods =
  | []
  | [Period1]
  | [Period1, Period1]
  | [Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1, Period1]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ]
  | [
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1,
      Period1
    ];
export type Role = string;
export type Sourceid3 = string;
export type Name = string;
export type Tempid1 = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Unitids1 = [string, ...string[]];
/**
 * @maxItems 100
 */
export type Subprojects = ProposedSubproject[];
export type Tempid2 = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Unitids2 = [string, ...string[]];
/**
 * @maxItems 100
 */
export type Jobs = ProposedJob[];
/**
 * @maxItems 40
 */
export type Languages1 = LanguageDetails[];
/**
 * @maxItems 100
 */
export type Privatedetails1 = PrivateDetails[];
export type Schemaversion = 1;
export type Disposition = "facts" | "administrative" | "duplicate" | "unresolved";
export type Duplicateof = string | null;
export type Facttempids = string[];
export type Sourceid4 = string;
export type Unitid2 = string;
/**
 * @maxItems 5000
 */
export type Units = UnitProposal[];
export type Sourcefingerprint = string;
export type Byteref = string;
export type Bytesha256 = string;
export type Id11 = string;
export type Mimetype = string;
export type Originalname = string;
export type Id12 = string;
export type Origin8 = "user";
export type Revision10 = number;
export type Text4 = string;
export type Unitid3 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision11 = number;
export type Disposition1 = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id13 = string;
export type Column = number | null;
export type Index = number;
export type Kind10 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order = number;
export type Representedfactids = string[];
export type Revision12 = number;
export type Text5 = string;
export type Units1 = SourceUnit[];
export type Warnings = string[];
export type Sources = Source[];

export interface GuiNormalizedResult {
  candidate: CandidateDetails;
  certifications: Certifications;
  education: Education;
  facts: Facts;
  fieldFactIds: Fieldfactids;
  languages: Languages;
  nameAssessment: NameAssessment;
  observationAssessment: ObservationAssessment;
  privateDetails: Privatedetails;
  rulesRevision: Rulesrevision;
  semanticProposal: GuiSemanticProposal;
  sourceFingerprint: Sourcefingerprint;
  sourceObservedAt: PartialDate | null;
  sources: Sources;
}
export interface CandidateDetails {
  location: SupportedText;
  name: SupportedText;
  title: SupportedText;
}
export interface SupportedText {
  evidence: Evidence;
  text: Text1;
}
export interface EvidenceSpan {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  text: Text;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface CertificationDetails {
  dateText: SupportedText;
  id: Id;
  issuer: SupportedText;
  name: SupportedText;
}
export interface EducationDetails {
  dateText: SupportedText;
  id: Id1;
  institution: SupportedText;
  qualification: SupportedText;
  specialty: SupportedText;
}
export interface TextFact {
  evidence: Evidence1;
  id: Id2;
  importance: Importance;
  jobId: Jobid;
  kind: Kind;
  origin: Origin;
  revision: Revision;
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
  text: Text2;
}
export interface TechnologyFact {
  evidence: Evidence3;
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
  evidence: Evidence4;
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
  period: Period;
  qualifiers: Qualifiers;
  result: Result;
  scope: Scope1;
  unit: Unit;
  upperNumber: Uppernumber;
}
export interface LeadershipFact {
  evidence: Evidence5;
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
  evidence: Evidence6;
  id: Id6;
  importance: Importance4;
  jobId: Jobid4;
  kind: Kind4;
  origin: Origin4;
  revision: Revision4;
  subprojectId: Subprojectid4;
  value: PartialDate;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface CandidateFact {
  evidence: Evidence7;
  id: Id7;
  importance: Importance5;
  jobId: Jobid5;
  kind: Kind5;
  origin: Origin5;
  revision: Revision5;
  subprojectId: Subprojectid5;
  value: CandidateDetail;
}
export interface CandidateDetail {
  field: Field;
  text: Text3;
}
export interface NameAssessmentFact {
  evidence: Evidence8;
  id: Id8;
  importance: Importance6;
  jobId: Jobid6;
  kind: Kind6;
  origin: Origin6;
  revision: Revision6;
  subprojectId: Subprojectid6;
  value: NameAssessment;
}
export interface NameAssessment {
  evidence: Evidence9;
  missingSurname: Missingsurname;
  revision: Revision7;
}
export interface ObservationFact {
  evidence: Evidence10;
  id: Id9;
  importance: Importance7;
  jobId: Jobid7;
  kind: Kind7;
  origin: Origin7;
  revision: Revision8;
  subprojectId: Subprojectid7;
  value: ObservationAssessment;
}
export interface ObservationAssessment {
  evidence: EvidenceSpan | null;
  revision: Revision9;
  sourceObservedAt: PartialDate | null;
}
export interface Fieldfactids {
  [k: string]: string[];
}
export interface LanguageDetails {
  id: Id10;
  name: SupportedText;
  proficiency: SupportedText;
}
export interface PrivateDetails {
  kind: Kind8;
  value: SupportedText;
}
export interface GuiSemanticProposal {
  candidate: CandidateDetails;
  certifications: Certifications1;
  education: Education1;
  facts: Facts1;
  jobs: Jobs;
  languages: Languages1;
  nameAssessment: NameAssessment;
  observationAssessment: ObservationAssessment;
  privateDetails: Privatedetails1;
  schemaVersion: Schemaversion;
  units: Units;
}
export interface ProposedFact {
  importance?: Importance8;
  jobTempId?: Jobtempid;
  kind: Kind9;
  sourceId: Sourceid2;
  subprojectTempId?: Subprojecttempid;
  tempId: Tempid;
  unitIds: Unitids;
  value: Value;
}
export interface ProposedJob {
  employer: Employer;
  periods: Periods;
  role: Role;
  sourceId: Sourceid3;
  subprojects?: Subprojects;
  tempId: Tempid2;
  unitIds: Unitids2;
}
export interface Period1 {
  end: PartialDate | null;
  start: PartialDate;
}
export interface ProposedSubproject {
  name: Name;
  period?: Period1 | null;
  tempId: Tempid1;
  unitIds: Unitids1;
}
export interface UnitProposal {
  disposition: Disposition;
  duplicateOf?: Duplicateof;
  factTempIds: Facttempids;
  sourceId: Sourceid4;
  unitId: Unitid2;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id11;
  mimeType: Mimetype;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision11;
  units: Units1;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id12;
  origin: Origin8;
  revision: Revision10;
  text: Text4;
  unitId: Unitid3;
}
export interface SourceUnit {
  disposition: Disposition1;
  id: Id13;
  location: SourceLocation;
  order: Order;
  representedFactIds: Representedfactids;
  revision: Revision12;
  text: Text5;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind10;
  row: Row;
}
