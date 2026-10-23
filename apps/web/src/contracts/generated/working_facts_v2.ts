export type Cellid = string;
export type Fieldkey = string;
export type Periodid = string | null;
export type Itemhandle = string;
export type Recordid = string;
export type Semanticschemahash = string;
export type Semantictype = string;
export type Builtinidentities = BuiltinItemIdentity[];
export type Active = boolean;
export type Admissionreceiptids = string[];
export type End = number;
export type Slicehash = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Start = number;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = SourceSpan[];
export type Fieldkey1 = string;
export type Id = string;
export type Manualscopeid = string | null;
export type Observationids = string[];
export type Origin = "model" | "source" | "human";
export type Rawinput = string;
export type Revision = number;
export type State = "admitted" | "human_raw" | "pending_manual" | "uncertain";
export type JsonValue = unknown;
export type Usercorrected = boolean;
export type Cells = ExtensionCell[];
export type Copyofrecordid = string | null;
export type Id1 = string;
export type Itemhandle1 = string;
export type Observationids1 = string[];
export type Active1 = boolean;
export type Id2 = string;
export type Kind = "owned_by" | "extension_of" | "related_to";
export type Revision1 = number;
export type Subjectid = string;
export type Targetid = string;
export type Relations = Relation[];
export type Revision2 = number;
export type Schemaversion = 1;
export type Semanticschemahash1 = string;
export type Semantictype1 = string;
export type Extensions = ExtensionRecord[];
export type Factcount = number;
export type Recoveredrows = number;
export type Requestbytes = number;
export type Status = "complete" | "partial";
export type Code = "FACT_SOURCE_UNRESOLVED" | "FACT_SECTION_OMITTED" | "FACT_ROWS_RECOVERED";
export type Page = number | null;
export type Section = string;
export type Sourceid1 = string;
export type Unitid1 = string | null;
/**
 * @maxItems 5000
 */
export type Unresolved = ExtractionIssue[];
export type Actionid = string;
export type Blockids = string[];
export type Cellids1 = string[];
export type Id3 = string;
export type Rawinput1 = string;
export type Manualscopes = ManualEditScope[];
export type Mode = "structured" | "digest" | "imported";
export type Admission = "provisional" | "accepted" | "rejected" | "uncertain";
export type Evidence1 = SourceSpan[];
export type Fieldkey2 = string;
export type Id4 = string;
export type Itemhandle2 = string;
export type Ownerrelations = Relation[];
export type Proposalhash = string;
export type Rawinput2 = string;
export type Receiptids = string[];
export type Observations = Observation[];
export type Sourceid2 = string;
export type Sourcerevision1 = number;
export type Text = string;
export type Unitid2 = string;
export type Unitrevision1 = number;
export type Evidence2 = EvidenceSpan[];
export type Id5 = string;
export type Kind1 = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext = string;
export type Revision3 = number;
export type Status1 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected1 = boolean;
export type Value = string | null;
export type Origin1 = "source" | "user";
export type Revision4 = number;
export type Usercorrected2 = boolean;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence3 = EvidenceSpan[];
export type Id6 = string;
export type Kind2 = "detail";
export type Label = string;
export type Origin2 = "source" | "user";
export type Revision5 = number;
export type Usercorrected3 = boolean;
export type Evidence4 = EvidenceSpan[];
export type Id7 = string;
export type Kind3 = "employment";
export type Origin3 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext1 = string;
export type Revision6 = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected4 = boolean;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Evidence5 = EvidenceSpan[];
export type Id8 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext2 = string;
export type Revision7 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected5 = boolean;
export type Value1 = boolean | null;
export type Revision8 = number;
export type Periods = WorkingPeriod[];
export type Revision9 = number;
export type Usercorrected6 = boolean;
export type Evidence6 = EvidenceSpan[];
export type Id9 = string;
export type Jobid = string;
export type Kind4 = "subproject";
export type Origin4 = "source" | "user";
export type Periods1 = WorkingPeriod[];
export type Revision10 = number;
export type Usercorrected7 = boolean;
export type Evidence7 = EvidenceSpan[];
export type Id10 = string;
export type Jobid1 = string | null;
export type Kind5 = "technology";
export type Origin5 = "source" | "user";
export type Revision11 = number;
export type Subprojectid = string | null;
export type Technical = boolean | null;
export type Usercorrected8 = boolean;
export type Evidence8 = EvidenceSpan[];
export type Id11 = string;
export type Kind6 = "education";
export type Origin6 = "source" | "user";
export type Revision12 = number;
export type Usercorrected9 = boolean;
export type Evidence9 = EvidenceSpan[];
export type Id12 = string;
export type Kind7 = "language";
export type Origin7 = "source" | "user";
export type Revision13 = number;
export type Usercorrected10 = boolean;
export type Evidence10 = EvidenceSpan[];
export type Id13 = string;
export type Kind8 = "certification";
export type Origin8 = "source" | "user";
export type Revision14 = number;
export type Usercorrected11 = boolean;
export type Evidence11 = EvidenceSpan[];
export type Id14 = string;
export type Jobid2 = string | null;
export type Kind9 = "claim";
export type Origin9 = "source" | "user";
export type Revision15 = number;
export type Subprojectid1 = string | null;
export type Usercorrected12 = boolean;
export type Evidence12 = EvidenceSpan[];
export type Id15 = string;
export type Jobid3 = string | null;
export type Kind10 = "metric";
export type Origin10 = "source" | "user";
export type Revision16 = number;
export type Subprojectid2 = string | null;
export type Usercorrected13 = boolean;
export type Pendingrawtext3 = string | null;
export type Rawtext3 = string;
export type Revision17 = number;
export type Status4 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected14 = boolean;
export type Attribution = "personal" | "team" | "organization" | "unknown";
export type Baseline = string | null;
export type Comparator = "exact" | "at_least" | "at_most" | "approximately" | "range";
export type Number = number;
export type Period = string | null;
export type Qualifiers = string[];
export type Result = string | null;
export type Scope = string | null;
export type Unit = string;
export type Uppernumber = number | null;
export type Evidence13 = EvidenceSpan[];
export type Id16 = string;
export type Jobid4 = string | null;
export type Kind11 = "leadership";
export type Origin11 = "source" | "user";
export type Revision18 = number;
export type Subprojectid3 = string | null;
export type Usercorrected15 = boolean;
export type Pendingrawtext4 = string | null;
export type Rawtext4 = string;
export type Revision19 = number;
export type Status5 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected16 = boolean;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Category = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence14 = EvidenceSpan[];
export type Id17 = string;
export type Kind12 = "unresolved";
export type Origin12 = "source" | "user";
export type Revision20 = number;
export type Status6 = "unresolved" | "pending" | "conflict";
export type Usercorrected17 = boolean;
export type Records = (
  | CandidateRecord
  | DetailRecord
  | EmploymentRecord
  | SubprojectRecord
  | TechnologyRecord
  | EducationRecord
  | LanguageRecord
  | CertificationRecord
  | ClaimRecord
  | MetricRecord
  | LeadershipRecord
  | UnresolvedRecord
)[];
export type Relations1 = Relation[];
export type Revision21 = number;
export type Schemaversion1 = 2;
export type Actionid1 = string;
export type Orderindex = number;
export type Recordid1 = string;
export type Revision22 = number;
export type Tombstones = RecordTombstone[];

export interface WorkingFactsV2 {
  builtinIdentities?: Builtinidentities;
  builtinManualScopes?: Builtinmanualscopes;
  extensions: Extensions;
  extraction?: ExtractionReport | null;
  manualScopes: Manualscopes;
  mode?: Mode;
  observations: Observations;
  records: Records;
  relations: Relations1;
  revision: Revision21;
  schemaVersion: Schemaversion1;
  tombstones: Tombstones;
}
export interface BuiltinItemIdentity {
  canonicalFields?: Canonicalfields;
  cellIds: Cellids;
  itemHandle: Itemhandle;
  periodIds?: Periodids;
  recordId: Recordid;
  semanticSchemaHash: Semanticschemahash;
  semanticType: Semantictype;
}
export interface Canonicalfields {
  [k: string]: CanonicalFieldBinding;
}
export interface CanonicalFieldBinding {
  cellId: Cellid;
  fieldKey: Fieldkey;
  periodId: Periodid;
}
export interface Cellids {
  [k: string]: string;
}
export interface Periodids {
  [k: string]: string;
}
export interface Builtinmanualscopes {
  [k: string]: string;
}
export interface ExtensionRecord {
  active: Active;
  cells: Cells;
  copyOfRecordId?: Copyofrecordid;
  id: Id1;
  itemHandle: Itemhandle1;
  observationIds: Observationids1;
  relations: Relations;
  retiredCellIds?: Retiredcellids;
  revision: Revision2;
  schemaVersion: Schemaversion;
  semanticSchemaHash: Semanticschemahash1;
  semanticType: Semantictype1;
}
export interface ExtensionCell {
  admissionReceiptIds: Admissionreceiptids;
  evidence: Evidence;
  fieldKey: Fieldkey1;
  id: Id;
  manualScopeId: Manualscopeid;
  observationIds: Observationids;
  origin: Origin;
  rawInput: Rawinput;
  revision: Revision;
  state: State;
  typedValue: JsonValue;
  userCorrected: Usercorrected;
}
export interface SourceSpan {
  end: End;
  sliceHash: Slicehash;
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  start: Start;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface Relation {
  active: Active1;
  id: Id2;
  kind: Kind;
  revision: Revision1;
  subjectId: Subjectid;
  targetId: Targetid;
}
export interface Retiredcellids {
  [k: string]: string;
}
export interface ExtractionReport {
  counts: Counts;
  factCount: Factcount;
  recoveredRows: Recoveredrows;
  requestBytes: Requestbytes;
  status: Status;
  unresolved: Unresolved;
}
export interface Counts {
  [k: string]: number;
}
export interface ExtractionIssue {
  code: Code;
  page?: Page;
  section: Section;
  sourceId: Sourceid1;
  unitId: Unitid1;
}
export interface ManualEditScope {
  actionId: Actionid;
  blockIds: Blockids;
  cellIds: Cellids1;
  id: Id3;
  rawInput: Rawinput1;
}
export interface Observation {
  admission: Admission;
  evidence: Evidence1;
  fieldKey: Fieldkey2;
  id: Id4;
  itemHandle: Itemhandle2;
  ownerRelations: Ownerrelations;
  proposalHash: Proposalhash;
  rawInput: Rawinput2;
  receiptIds: Receiptids;
  typedValue: JsonValue;
}
export interface CandidateRecord {
  evidence: Evidence2;
  id: Id5;
  kind: Kind1;
  location: WorkingFieldStr;
  name: WorkingFieldStr;
  origin: Origin1;
  revision: Revision4;
  title: WorkingFieldStr;
  userCorrected?: Usercorrected2;
}
export interface EvidenceSpan {
  sourceId: Sourceid2;
  sourceRevision: Sourcerevision1;
  text: Text;
  unitId: Unitid2;
  unitRevision: Unitrevision1;
}
export interface WorkingFieldStr {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext;
  revision: Revision3;
  status: Status1;
  userCorrected?: Usercorrected1;
  value: Value;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence3;
  id: Id6;
  kind: Kind2;
  label: Label;
  origin: Origin2;
  revision: Revision5;
  userCorrected?: Usercorrected3;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence4;
  id: Id7;
  kind: Kind3;
  origin: Origin3;
  periods: Periods;
  revision: Revision9;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected6;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence5;
  id: Id8;
  present: WorkingFieldBool;
  revision: Revision8;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext1;
  revision: Revision6;
  status: Status2;
  userCorrected?: Usercorrected4;
  value: PartialDate | null;
}
export interface PartialDate {
  day: Day;
  month: Month;
  precision: Precision;
  year: Year;
}
export interface WorkingFieldBool {
  pendingRawText: Pendingrawtext2;
  rawText: Rawtext2;
  revision: Revision7;
  status: Status3;
  userCorrected?: Usercorrected5;
  value: Value1;
}
export interface SubprojectRecord {
  evidence: Evidence6;
  id: Id9;
  jobId: Jobid;
  kind: Kind4;
  name: WorkingFieldStr;
  origin: Origin4;
  periods: Periods1;
  revision: Revision10;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected7;
}
export interface TechnologyRecord {
  canonicalId: WorkingFieldStr;
  display: WorkingFieldStr;
  evidence: Evidence7;
  experience?: WorkingFieldStr;
  id: Id10;
  jobId: Jobid1;
  kind: Kind5;
  origin: Origin5;
  revision: Revision11;
  subprojectId: Subprojectid;
  technical?: Technical;
  userCorrected?: Usercorrected8;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence8;
  id: Id11;
  institution: WorkingFieldStr;
  kind: Kind6;
  origin: Origin6;
  qualification: WorkingFieldStr;
  revision: Revision12;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected9;
}
export interface LanguageRecord {
  evidence: Evidence9;
  id: Id12;
  kind: Kind7;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin7;
  revision: Revision13;
  userCorrected?: Usercorrected10;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence10;
  id: Id13;
  issuer: WorkingFieldStr;
  kind: Kind8;
  name: WorkingFieldStr;
  origin: Origin8;
  revision: Revision14;
  userCorrected?: Usercorrected11;
}
export interface ClaimRecord {
  evidence: Evidence11;
  id: Id14;
  jobId: Jobid2;
  kind: Kind9;
  origin: Origin9;
  revision: Revision15;
  subprojectId: Subprojectid1;
  userCorrected?: Usercorrected12;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence12;
  id: Id15;
  jobId: Jobid3;
  kind: Kind10;
  origin: Origin10;
  revision: Revision16;
  subprojectId: Subprojectid2;
  userCorrected?: Usercorrected13;
  value: WorkingFieldMetricValue;
}
export interface WorkingFieldMetricValue {
  pendingRawText: Pendingrawtext3;
  rawText: Rawtext3;
  revision: Revision17;
  status: Status4;
  userCorrected?: Usercorrected14;
  value: MetricValue | null;
}
export interface MetricValue {
  attribution: Attribution;
  baseline: Baseline;
  comparator: Comparator;
  number: Number;
  period: Period;
  qualifiers: Qualifiers;
  result: Result;
  scope: Scope;
  unit: Unit;
  upperNumber: Uppernumber;
}
export interface LeadershipRecord {
  evidence: Evidence13;
  id: Id16;
  jobId: Jobid4;
  kind: Kind11;
  origin: Origin11;
  revision: Revision18;
  subprojectId: Subprojectid3;
  userCorrected?: Usercorrected15;
  value: WorkingFieldLeadershipValue;
}
export interface WorkingFieldLeadershipValue {
  pendingRawText: Pendingrawtext4;
  rawText: Rawtext4;
  revision: Revision19;
  status: Status5;
  userCorrected?: Usercorrected16;
  value: LeadershipValue | null;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface UnresolvedRecord {
  category: Category;
  evidence: Evidence14;
  id: Id17;
  kind: Kind12;
  origin: Origin12;
  revision: Revision20;
  status: Status6;
  userCorrected?: Usercorrected17;
}
export interface RecordTombstone {
  actionId: Actionid1;
  orderIndex: Orderindex;
  recordId: Recordid1;
  revision: Revision22;
}
