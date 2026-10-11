export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Baserevision = number;
export type Preservemanualprofile = boolean;
export type Canonicalid = string | null;
export type Confident = boolean;
export type Id = string;
export type Kind = "technology" | "date";
export type Sourceid = string;
export type Text = string;
export type Unitid = string;
/**
 * @maxItems 500
 */
export type Candidates = LiteralCandidate[];
export type Employer = string;
export type Factids = string[];
export type Id1 = string;
export type Periods = Period[];
export type Reviewrequired = true;
export type Role = string;
export type Sourceid1 = string;
export type Id2 = string;
export type Name = string;
export type Sourceid2 = string;
export type Unitids = string[];
export type Subprojects = ReviewedSubproject[];
export type Unitids1 = string[];
export type Employment = ReviewedEmployment[];
export type Sourceid3 = string;
export type Sourcerevision = number;
export type Unitid1 = string;
export type Unitrevision = number;
export type Evidence = Evidence1[];
export type Id3 = string;
export type Importance = "essential" | "normal" | "minor";
export type Jobid = string | null;
export type Kind1 = "text";
export type Origin = "source" | "user";
export type Revision = number;
export type Subprojectid = string | null;
export type Text1 = string;
export type Evidence2 = Evidence1[];
export type Id4 = string;
export type Importance1 = "essential" | "normal" | "minor";
export type Jobid1 = string | null;
export type Kind2 = "technology";
export type Origin1 = "source" | "user";
export type Revision1 = number;
export type Subprojectid1 = string | null;
export type Canonicalid1 = string;
export type Display = string;
export type Scope = "global" | "job" | "subproject";
export type Evidence3 = Evidence1[];
export type Id5 = string;
export type Importance2 = "essential" | "normal" | "minor";
export type Jobid2 = string | null;
export type Kind3 = "metric";
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
export type Id6 = string;
export type Importance3 = "essential" | "normal" | "minor";
export type Jobid3 = string | null;
export type Kind4 = "leadership";
export type Origin3 = "source" | "user";
export type Revision3 = number;
export type Subprojectid3 = string | null;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Evidence5 = Evidence1[];
export type Id7 = string;
export type Importance4 = "essential" | "normal" | "minor";
export type Jobid4 = string | null;
export type Kind5 = "date";
export type Origin4 = "source" | "user";
export type Revision4 = number;
export type Subprojectid4 = string | null;
/**
 * @maxItems 1000
 */
export type Facts = (TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact)[];
export type Code =
  "NARRATIVE_REVIEW" | "AMBIGUOUS_DATE" | "AMBIGUOUS_TECHNOLOGY" | "EXTRACTION_GAP" | "SEMANTIC_REVIEW";
export type Id8 = string;
export type Message = string;
export type Sourceid4 = string;
export type Unitid2 = string | null;
/**
 * @maxItems 20000
 */
export type Issues = ReviewIssue[];
export type Proposedfactids = string[];
export type Revision5 = number;
export type Sourcefingerprint = string;
export type Transportversion = 1;
export type Disposition = "facts" | "administrative" | "duplicate" | "unresolved";
export type Duplicateof = string | null;
export type Factids1 = string[];
export type Sourceid5 = string;
export type Unitid3 = string;
/**
 * @maxItems 10000
 */
export type Units = UnitAccount[];
export type Sourcefingerprint1 = string;
export type Sourcelanguage = "ru" | "en" | "mixed";
export type Transportversion1 = 1;

export interface DraftRequest {
  asOf: PartialDate;
  baseRevision: Baserevision;
  preserveManualProfile?: Preservemanualprofile;
  sheet: FactSheet;
  sourceFingerprint: Sourcefingerprint1;
  sourceLanguage: Sourcelanguage;
  transportVersion?: Transportversion1;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface FactSheet {
  candidates: Candidates;
  employment?: Employment;
  facts: Facts;
  issues: Issues;
  overlayFactRefs?: Overlayfactrefs;
  proposedFactIds?: Proposedfactids;
  revision?: Revision5;
  sourceFingerprint: Sourcefingerprint;
  transportVersion?: Transportversion;
  units: Units;
  userCorrections?: Usercorrections;
}
export interface LiteralCandidate {
  canonicalId?: Canonicalid;
  confident: Confident;
  id: Id;
  kind: Kind;
  sourceId: Sourceid;
  text: Text;
  unitId: Unitid;
}
export interface ReviewedEmployment {
  employer: Employer;
  factIds: Factids;
  id: Id1;
  periods: Periods;
  reviewRequired?: Reviewrequired;
  role: Role;
  sourceId: Sourceid1;
  subprojects: Subprojects;
  unitIds: Unitids1;
}
export interface Period {
  end: PartialDate | null;
  start: PartialDate;
}
export interface ReviewedSubproject {
  id: Id2;
  name: Name;
  period?: Period | null;
  sourceId: Sourceid2;
  unitIds: Unitids;
}
export interface TextFact {
  evidence: Evidence;
  id: Id3;
  importance: Importance;
  jobId: Jobid;
  kind: Kind1;
  origin: Origin;
  revision: Revision;
  subprojectId: Subprojectid;
  value: TextValue;
}
export interface Evidence1 {
  sourceId: Sourceid3;
  sourceRevision: Sourcerevision;
  unitId: Unitid1;
  unitRevision: Unitrevision;
}
export interface TextValue {
  text: Text1;
}
export interface TechnologyFact {
  evidence: Evidence2;
  id: Id4;
  importance: Importance1;
  jobId: Jobid1;
  kind: Kind2;
  origin: Origin1;
  revision: Revision1;
  subprojectId: Subprojectid1;
  value: TechnologyValue;
}
export interface TechnologyValue {
  canonicalId: Canonicalid1;
  display: Display;
  scope: Scope;
}
export interface MetricFact {
  evidence: Evidence3;
  id: Id5;
  importance: Importance2;
  jobId: Jobid2;
  kind: Kind3;
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
  id: Id6;
  importance: Importance3;
  jobId: Jobid3;
  kind: Kind4;
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
  id: Id7;
  importance: Importance4;
  jobId: Jobid4;
  kind: Kind5;
  origin: Origin4;
  revision: Revision4;
  subprojectId: Subprojectid4;
  value: PartialDate;
}
export interface ReviewIssue {
  code: Code;
  id: Id8;
  message: Message;
  sourceId: Sourceid4;
  unitId?: Unitid2;
}
export interface Overlayfactrefs {
  [k: string]: Evidence1[];
}
export interface UnitAccount {
  disposition: Disposition;
  duplicateOf?: Duplicateof;
  factIds: Factids1;
  sourceId: Sourceid5;
  unitId: Unitid3;
}
export interface Usercorrections {
  [k: string]: string;
}
