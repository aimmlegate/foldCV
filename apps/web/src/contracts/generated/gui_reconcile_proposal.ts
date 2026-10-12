export type Anchor = FieldAnchor | SectionAnchor | DocumentAnchor;
export type Fieldid = string;
export type Kind = "field";
export type End = number;
export type Start = number;
export type Kind1 = "section";
export type Sectionid = string;
export type Kind2 = "document";
export type Code = string;
/**
 * @maxItems 100
 */
export type Factids = string[];
export type Id = string;
export type Reason = string;
export type Type = "missing" | "conflicting" | "warning";
export type Updatesuggestionid = string | null;
/**
 * @maxItems 500
 */
export type Annotations = SemanticMark[];
export type Factids1 = string[];
export type Catalogid = string;
export type Display = string;
export type Factids2 = string[];
export type Focus = PlanFocus[];
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Disposition = "detailed" | "early-career";
export type Factids3 = string[];
export type Jobid = string;
export type Jobs = JobDisposition[];
export type Origin = "model" | "migration";
export type Profilelanguage = ("ru" | "en") | null;
export type Revision = number;
export type Rulesrevision = number | null;
export type Sourcelanguage = "ru" | "en" | "mixed";
export type Factids4 = string[];
export type Title = string;
export type Technologygroups = TechnologyGroup[];
export type Sourceid = string;
export type Sourcerevision = number;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = Evidence1[];
export type Id1 = string;
export type Importance = "essential" | "normal" | "minor";
export type Jobid1 = string | null;
export type Kind3 = "text";
export type Sourceid1 = string;
export type Sourcerevision1 = number;
export type Text = string;
export type Unitid1 = string;
export type Unitrevision1 = number;
export type Literalevidence = EvidenceSpan[];
export type Origin1 = "source" | "user";
export type Revision1 = number;
export type Subprojectid = string | null;
export type Text1 = string;
export type Evidence2 = Evidence1[];
export type Id2 = string;
export type Importance1 = "essential" | "normal" | "minor";
export type Jobid2 = string | null;
export type Kind4 = "technology";
export type Literalevidence1 = EvidenceSpan[];
export type Origin2 = "source" | "user";
export type Revision2 = number;
export type Subprojectid1 = string | null;
export type Canonicalid = string;
export type Display1 = string;
export type Scope = "global" | "job" | "subproject";
export type Evidence3 = Evidence1[];
export type Id3 = string;
export type Importance2 = "essential" | "normal" | "minor";
export type Jobid3 = string | null;
export type Kind5 = "metric";
export type Literalevidence2 = EvidenceSpan[];
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
export type Evidence4 = Evidence1[];
export type Id4 = string;
export type Importance3 = "essential" | "normal" | "minor";
export type Jobid4 = string | null;
export type Kind6 = "leadership";
export type Literalevidence3 = EvidenceSpan[];
export type Origin4 = "source" | "user";
export type Revision4 = number;
export type Subprojectid3 = string | null;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Evidence5 = Evidence1[];
export type Id5 = string;
export type Importance4 = "essential" | "normal" | "minor";
export type Jobid5 = string | null;
export type Kind7 = "date";
export type Literalevidence4 = EvidenceSpan[];
export type Origin5 = "source" | "user";
export type Revision5 = number;
export type Subprojectid4 = string | null;
export type Evidence6 = Evidence1[];
export type Id6 = string;
export type Importance5 = "essential" | "normal" | "minor";
export type Jobid6 = string | null;
export type Kind8 = "text";
export type Origin6 = "source" | "user";
export type Revision6 = number;
export type Subprojectid5 = string | null;
export type Evidence7 = Evidence1[];
export type Id7 = string;
export type Importance6 = "essential" | "normal" | "minor";
export type Jobid7 = string | null;
export type Kind9 = "technology";
export type Origin7 = "source" | "user";
export type Revision7 = number;
export type Subprojectid6 = string | null;
export type Evidence8 = Evidence1[];
export type Id8 = string;
export type Importance7 = "essential" | "normal" | "minor";
export type Jobid8 = string | null;
export type Kind10 = "metric";
export type Origin8 = "source" | "user";
export type Revision8 = number;
export type Subprojectid7 = string | null;
export type Evidence9 = Evidence1[];
export type Id9 = string;
export type Importance8 = "essential" | "normal" | "minor";
export type Jobid9 = string | null;
export type Kind11 = "leadership";
export type Origin9 = "source" | "user";
export type Revision9 = number;
export type Subprojectid8 = string | null;
export type Evidence10 = Evidence1[];
export type Id10 = string;
export type Importance9 = "essential" | "normal" | "minor";
export type Jobid10 = string | null;
export type Kind12 = "date";
export type Origin10 = "source" | "user";
export type Revision10 = number;
export type Subprojectid9 = string | null;
export type Evidence11 = Evidence1[];
export type Id11 = string;
export type Importance10 = "essential" | "normal" | "minor";
export type Jobid11 = string | null;
export type Kind13 = "candidate_detail";
export type Origin11 = "source" | "user";
export type Revision11 = number;
export type Subprojectid10 = string | null;
export type Field = "name" | "title" | "location" | "education" | "certification" | "language" | "private_metadata";
export type Fieldid1 = string | null;
export type Text2 = string;
export type Evidence12 = Evidence1[];
export type Id12 = string;
export type Importance11 = "essential" | "normal" | "minor";
export type Jobid12 = string | null;
export type Kind14 = "name_assessment";
export type Origin12 = "source" | "user";
export type Revision12 = number;
export type Subprojectid11 = string | null;
export type Evidence13 = EvidenceSpan[];
export type Missingsurname = boolean | null;
export type Revision13 = number;
export type Evidence14 = Evidence1[];
export type Id13 = string;
export type Importance12 = "essential" | "normal" | "minor";
export type Jobid13 = string | null;
export type Kind15 = "source_observation";
export type Origin13 = "source" | "user";
export type Revision14 = number;
export type Subprojectid12 = string | null;
export type Revision15 = number;
export type Evidence15 = Evidence1[];
export type Id14 = string;
export type Importance13 = "essential" | "normal" | "minor";
export type Jobid14 = string | null;
export type Kind16 = "employment";
export type Literalevidence5 = EvidenceSpan[];
export type Origin14 = "source" | "user";
export type Revision16 = number;
export type Subprojectid13 = string | null;
export type Employer = string;
export type Jobid15 = string;
export type Endtext = string;
export type Evidence16 = EvidenceSpan[];
export type Id15 = string;
export type Present = boolean;
export type Starttext = string;
export type Periods = EmploymentPeriodValue[];
export type Role = string;
export type Factids5 = string[];
export type Id16 = string;
export type Name = string;
export type Subprojects = Subproject[];
/**
 * @maxItems 500
 */
export type Facts = (
  | (GuiTextFact | GuiTechnologyFact | GuiMetricFact | GuiLeadershipFact | GuiDateFact)
  | (TextFact | TechnologyFact | MetricFact | LeadershipFact | DateFact)
  | CandidateFact
  | NameAssessmentFact
  | ObservationFact
  | EmploymentFact
)[];
/**
 * @maxItems 100
 */
export type Factids6 = string[];
export type Fieldid2 = string;
/**
 * @maxItems 500
 */
export type Fieldfacts = ReconciledField[];
/**
 * @maxItems 50
 */
export type Recommendations = string[];
/**
 * @maxItems 100
 */
export type Factids7 = string[];
export type Id17 = string;
export type Reason1 = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Replacements = [FieldReplacement, ...FieldReplacement[]];
export type Fieldid3 = string;
export type Text3 = string;
/**
 * @maxItems 100
 */
export type Suggestions = SuggestedUpdate[];

export interface GuiReconcileProposal {
  annotations: Annotations;
  editorialPlan: EditorialPlan | null;
  facts: Facts;
  fieldFacts: Fieldfacts;
  recommendations: Recommendations;
  suggestions: Suggestions;
}
export interface SemanticMark {
  anchor: Anchor;
  code: Code;
  factIds: Factids;
  id: Id;
  reason: Reason;
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
export interface EditorialPlan {
  factIds: Factids1;
  focus: Focus;
  formattingAsOf: PartialDate;
  jobs: Jobs;
  origin: Origin;
  profileLanguage: Profilelanguage;
  revision: Revision;
  rulesRevision: Rulesrevision;
  sourceLanguage: Sourcelanguage;
  technologyGroups: Technologygroups;
}
export interface PlanFocus {
  catalogId: Catalogid;
  display: Display;
  factIds: Factids2;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface JobDisposition {
  disposition: Disposition;
  factIds: Factids3;
  jobId: Jobid;
}
export interface TechnologyGroup {
  factIds: Factids4;
  title: Title;
}
export interface GuiTextFact {
  evidence: Evidence;
  id: Id1;
  importance: Importance;
  jobId: Jobid1;
  kind: Kind3;
  literalEvidence: Literalevidence;
  origin: Origin1;
  revision: Revision1;
  subprojectId: Subprojectid;
  value: TextValue;
}
export interface Evidence1 {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface EvidenceSpan {
  sourceId: Sourceid1;
  sourceRevision: Sourcerevision1;
  text: Text;
  unitId: Unitid1;
  unitRevision: Unitrevision1;
}
export interface TextValue {
  text: Text1;
}
export interface GuiTechnologyFact {
  evidence: Evidence2;
  id: Id2;
  importance: Importance1;
  jobId: Jobid2;
  kind: Kind4;
  literalEvidence: Literalevidence1;
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
export interface GuiMetricFact {
  evidence: Evidence3;
  id: Id3;
  importance: Importance2;
  jobId: Jobid3;
  kind: Kind5;
  literalEvidence: Literalevidence2;
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
export interface GuiLeadershipFact {
  evidence: Evidence4;
  id: Id4;
  importance: Importance3;
  jobId: Jobid4;
  kind: Kind6;
  literalEvidence: Literalevidence3;
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
export interface GuiDateFact {
  evidence: Evidence5;
  id: Id5;
  importance: Importance4;
  jobId: Jobid5;
  kind: Kind7;
  literalEvidence: Literalevidence4;
  origin: Origin5;
  revision: Revision5;
  subprojectId: Subprojectid4;
  value: PartialDate;
}
export interface TextFact {
  evidence: Evidence6;
  id: Id6;
  importance: Importance5;
  jobId: Jobid6;
  kind: Kind8;
  origin: Origin6;
  revision: Revision6;
  subprojectId: Subprojectid5;
  value: TextValue;
}
export interface TechnologyFact {
  evidence: Evidence7;
  id: Id7;
  importance: Importance6;
  jobId: Jobid7;
  kind: Kind9;
  origin: Origin7;
  revision: Revision7;
  subprojectId: Subprojectid6;
  value: TechnologyValue;
}
export interface MetricFact {
  evidence: Evidence8;
  id: Id8;
  importance: Importance7;
  jobId: Jobid8;
  kind: Kind10;
  origin: Origin8;
  revision: Revision8;
  subprojectId: Subprojectid7;
  value: MetricValue;
}
export interface LeadershipFact {
  evidence: Evidence9;
  id: Id9;
  importance: Importance8;
  jobId: Jobid9;
  kind: Kind11;
  origin: Origin9;
  revision: Revision9;
  subprojectId: Subprojectid8;
  value: LeadershipValue;
}
export interface DateFact {
  evidence: Evidence10;
  id: Id10;
  importance: Importance9;
  jobId: Jobid10;
  kind: Kind12;
  origin: Origin10;
  revision: Revision10;
  subprojectId: Subprojectid9;
  value: PartialDate;
}
export interface CandidateFact {
  evidence: Evidence11;
  id: Id11;
  importance: Importance10;
  jobId: Jobid11;
  kind: Kind13;
  origin: Origin11;
  revision: Revision11;
  subprojectId: Subprojectid10;
  value: CandidateDetail;
}
export interface CandidateDetail {
  field: Field;
  fieldId?: Fieldid1;
  text: Text2;
}
export interface NameAssessmentFact {
  evidence: Evidence12;
  id: Id12;
  importance: Importance11;
  jobId: Jobid12;
  kind: Kind14;
  origin: Origin12;
  revision: Revision12;
  subprojectId: Subprojectid11;
  value: NameAssessment;
}
export interface NameAssessment {
  evidence: Evidence13;
  missingSurname: Missingsurname;
  revision: Revision13;
}
export interface ObservationFact {
  evidence: Evidence14;
  id: Id13;
  importance: Importance12;
  jobId: Jobid13;
  kind: Kind15;
  origin: Origin13;
  revision: Revision14;
  subprojectId: Subprojectid12;
  value: ObservationAssessment;
}
export interface ObservationAssessment {
  evidence: EvidenceSpan | null;
  revision: Revision15;
  sourceObservedAt: PartialDate | null;
}
export interface EmploymentFact {
  evidence: Evidence15;
  id: Id14;
  importance: Importance13;
  jobId: Jobid14;
  kind: Kind16;
  literalEvidence: Literalevidence5;
  origin: Origin14;
  revision: Revision16;
  subprojectId: Subprojectid13;
  value: EmploymentValue;
}
export interface EmploymentValue {
  employer: Employer;
  jobId: Jobid15;
  periods: Periods;
  role: Role;
  subprojects: Subprojects;
}
export interface EmploymentPeriodValue {
  end: PartialDate | null;
  endText: Endtext;
  evidence: Evidence16;
  id: Id15;
  present: Present;
  start: PartialDate | null;
  startText: Starttext;
}
export interface Subproject {
  factIds: Factids5;
  id: Id16;
  name: Name;
  period: Period1 | null;
}
export interface Period1 {
  end: PartialDate | null;
  start: PartialDate;
}
export interface ReconciledField {
  factIds: Factids6;
  fieldId: Fieldid2;
}
export interface SuggestedUpdate {
  factIds: Factids7;
  id: Id17;
  reason: Reason1;
  replacements: Replacements;
}
export interface FieldReplacement {
  fieldId: Fieldid3;
  range: Range | null;
  text: Text3;
}
