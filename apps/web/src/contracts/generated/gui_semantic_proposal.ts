export type Sourceid = string;
export type Sourcerevision = number;
export type Text = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Text1 = string;
export type Id = string;
/**
 * @maxItems 40
 */
export type Certifications = CertificationDetails[];
export type Id1 = string;
/**
 * @maxItems 40
 */
export type Education = EducationDetails[];
export type Importance = "essential" | "normal" | "minor";
export type Jobtempid = string | null;
export type Kind = "text" | "technology" | "date" | "metric" | "leadership";
export type Literalevidence = EvidenceSpan[];
export type Sourceid1 = string;
export type Subprojecttempid = string | null;
export type Tempid = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Unitids = [string, ...string[]];
export type Value = TextValue | TechnologyValue | PartialDate | MetricValue | LeadershipValue;
export type Text2 = string;
export type Canonicalid = string;
export type Display = string;
export type Scope = "global" | "job" | "subproject";
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
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
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
/**
 * @maxItems 500
 */
export type Facts = GuiFactProposal[];
export type Employer = string;
/**
 * @maxItems 20
 */
export type Periods =
  | []
  | [GuiPeriodProposal]
  | [GuiPeriodProposal, GuiPeriodProposal]
  | [GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal]
  | [GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal]
  | [GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal]
  | [GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal, GuiPeriodProposal]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ]
  | [
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal,
      GuiPeriodProposal
    ];
export type Endtext = string | null;
export type Evidence1 = EvidenceSpan[];
export type Present = boolean;
export type Starttext = string | null;
export type Role = string;
export type Sourceid2 = string;
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
export type Jobs = GuiJobProposal[];
export type Id2 = string;
/**
 * @maxItems 40
 */
export type Languages = LanguageDetails[];
export type Evidence2 = EvidenceSpan[];
export type Missingsurname = boolean | null;
export type Revision = number;
export type Revision1 = number;
export type Kind1 = "phone" | "email" | "messenger" | "birth_date" | "age" | "platform_metadata";
/**
 * @maxItems 100
 */
export type Privatedetails = PrivateDetails[];
export type Schemaversion = 1;
export type Disposition = "facts" | "administrative" | "duplicate" | "unresolved";
export type Duplicateof = string | null;
export type Facttempids = string[];
export type Sourceid3 = string;
export type Unitid1 = string;
/**
 * @maxItems 5000
 */
export type Units = UnitProposal[];

export interface GuiSemanticProposal {
  candidate: CandidateDetails;
  certifications: Certifications;
  education: Education;
  facts: Facts;
  jobs: Jobs;
  languages: Languages;
  nameAssessment: NameAssessment;
  observationAssessment: ObservationAssessment;
  privateDetails: Privatedetails;
  schemaVersion: Schemaversion;
  units: Units;
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
export interface GuiFactProposal {
  importance?: Importance;
  jobTempId?: Jobtempid;
  kind: Kind;
  literalEvidence?: Literalevidence;
  sourceId: Sourceid1;
  subprojectTempId?: Subprojecttempid;
  tempId: Tempid;
  unitIds: Unitids;
  value: Value;
}
export interface TextValue {
  text: Text2;
}
export interface TechnologyValue {
  canonicalId: Canonicalid;
  display: Display;
  scope: Scope;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
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
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface GuiJobProposal {
  employer: Employer;
  periods: Periods;
  role: Role;
  sourceId: Sourceid2;
  subprojects?: Subprojects;
  tempId: Tempid2;
  unitIds: Unitids2;
}
export interface GuiPeriodProposal {
  end: PartialDate | null;
  endText?: Endtext;
  evidence?: Evidence1;
  present?: Present;
  start: PartialDate | null;
  startText?: Starttext;
}
export interface ProposedSubproject {
  name: Name;
  period?: Period1 | null;
  tempId: Tempid1;
  unitIds: Unitids1;
}
export interface Period1 {
  end: PartialDate | null;
  start: PartialDate;
}
export interface LanguageDetails {
  id: Id2;
  name: SupportedText;
  proficiency: SupportedText;
}
export interface NameAssessment {
  evidence: Evidence2;
  missingSurname: Missingsurname;
  revision: Revision;
}
export interface ObservationAssessment {
  evidence: EvidenceSpan | null;
  revision: Revision1;
  sourceObservedAt: PartialDate | null;
}
export interface PrivateDetails {
  kind: Kind1;
  value: SupportedText;
}
export interface UnitProposal {
  disposition: Disposition;
  duplicateOf?: Duplicateof;
  factTempIds: Facttempids;
  sourceId: Sourceid3;
  unitId: Unitid1;
}
