export type Height = number;
export type Id = string;
export type Mimetype = "image/png" | "image/jpeg";
export type Path = string;
export type Sha256 = string;
export type Size = number;
export type Width = number;
export type Assets = LocalImageAsset[];
export type Createdat = string;
/**
 * @minItems 3
 * @maxItems 3
 */
export type Regions = [RichRegion, RichRegion, RichRegion];
export type Children11 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Backgroundcolor = string;
export type Bold = boolean;
export type Code = boolean;
export type Italic = boolean;
export type Strike = boolean;
export type Textcolor = string;
export type Underline = boolean;
export type Text = string;
export type Type = "text";
export type Content1 = StyledText[];
export type Href = string;
export type Type1 = "link";
export type Bindingid = string;
export type Fieldkey = string;
export type Recordid = string;
export type Syncedfactrevision = number;
export type Text1 = string;
export type Type2 = "fact_field";
export type Content = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id1 = string;
export type Alignment = "left" | "center" | "right" | "justify";
export type Backgroundcolor1 = string;
export type Presentation = "standard" | "focus";
export type Recordid1 = string | null;
export type Textcolor1 = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Text2 = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Fieldkeys = string[];
export type Id2 = string;
export type Kind = "citation";
export type Recordid2 = string;
export type Fieldkey1 = string;
export type Id3 = string;
export type Kind1 = "field_binding";
export type Recordid3 = string;
export type Id4 = string;
export type Kind2 = "working_owner";
export type Recordid4 = string;
/**
 * @minItems 1
 */
export type Evidence1 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id5 = string;
export type Kind3 = "source";
export type Provenance = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision = number;
export type Type3 = "section";
export type Children10 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content2 = null;
export type Id6 = string;
export type Alignment1 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (StyledText | Hyperlink | FactFieldSpan)[];
export type Height1 = number;
export type Width1 = number;
export type Provenance1 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision1 = number;
export type Type4 = "image";
export type Children9 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
/**
 * @minItems 1
 */
export type Columnwidths = [number | null, ...(number | null)[]];
export type Headerrows = number;
/**
 * @minItems 1
 */
export type Rows = [TableRow, ...TableRow[]];
/**
 * @minItems 1
 */
export type Cells = [TableCell, ...TableCell[]];
export type Alignment2 = "left" | "center" | "right" | "justify";
export type Backgroundcolor2 = string;
export type Colspan = number;
export type Content3 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id7 = string;
export type Revision2 = number;
export type Rowspan = number;
export type Id8 = string;
export type Id9 = string;
export type Alignment3 = "left" | "center" | "right" | "justify";
export type Backgroundcolor3 = string;
export type Textcolor2 = string;
export type Provenance2 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision3 = number;
export type Type5 = "table";
export type Children8 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content4 = null;
export type Id10 = string;
export type Provenance3 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision4 = number;
export type Type6 = "divider";
export type Children7 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content5 = string;
export type Id11 = string;
export type Backgroundcolor4 = string;
export type Language = string;
export type Provenance4 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision5 = number;
export type Type7 = "code";
export type Children6 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content6 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id12 = string;
export type Provenance5 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision6 = number;
export type Type8 = "quote";
export type Children5 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content7 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id13 = string;
export type Provenance6 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision7 = number;
export type Type9 = "toggle_list";
export type Children4 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content8 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id14 = string;
export type Alignment4 = "left" | "center" | "right" | "justify";
export type Backgroundcolor5 = string;
export type Checked = boolean;
export type Textcolor3 = string;
export type Provenance7 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision8 = number;
export type Type10 = "check_list";
export type Children3 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content9 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id15 = string;
export type Alignment5 = "left" | "center" | "right" | "justify";
export type Backgroundcolor6 = string;
export type Start = number;
export type Textcolor4 = string;
export type Provenance8 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision9 = number;
export type Type11 = "numbered_list";
export type Children2 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content10 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id16 = string;
export type Provenance9 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision10 = number;
export type Type12 = "bullet_list";
export type Children1 = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content11 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id17 = string;
export type Alignment6 = "left" | "center" | "right" | "justify";
export type Backgroundcolor7 = string;
export type Level = 1 | 2 | 3;
export type Textcolor5 = string;
export type Provenance10 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision11 = number;
export type Type13 = "heading";
export type Children = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Content12 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id18 = string;
export type Provenance11 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision12 = number;
export type Type14 = "paragraph";
export type Blocks = (
  | ParagraphBlock
  | HeadingBlock
  | BulletBlock
  | NumberedBlock
  | ChecklistBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | DividerBlock
  | TableBlock
  | ImageBlock
  | SectionBlock
)[];
export type Id19 = string;
export type Revision13 = number;
export type Role = "header" | "sidebar" | "main";
export type Revision14 = number;
export type Schemaversion = 1;
export type Evidence2 = EvidenceSpan[];
export type Id20 = string;
export type Rawtext = string;
export type Evidencerecords = ImmutableFactEvidence[];
export type Evidence3 = EvidenceSpan[];
export type Id21 = string;
export type Kind4 = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext1 = string;
export type Revision15 = number;
export type Status = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Value = string | null;
export type Origin = "source" | "user";
export type Revision16 = number;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence4 = EvidenceSpan[];
export type Id22 = string;
export type Kind5 = "detail";
export type Label = string;
export type Origin1 = "source" | "user";
export type Revision17 = number;
export type Evidence5 = EvidenceSpan[];
export type Id23 = string;
export type Kind6 = "employment";
export type Origin2 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext2 = string;
export type Revision18 = number;
export type Status1 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Evidence6 = EvidenceSpan[];
export type Id24 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext3 = string;
export type Revision19 = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Value1 = boolean | null;
export type Revision20 = number;
export type Periods = WorkingPeriod[];
export type Revision21 = number;
export type Evidence7 = EvidenceSpan[];
export type Id25 = string;
export type Jobid = string;
export type Kind7 = "subproject";
export type Origin3 = "source" | "user";
export type Periods1 = WorkingPeriod[];
export type Revision22 = number;
export type Evidence8 = EvidenceSpan[];
export type Id26 = string;
export type Jobid1 = string | null;
export type Kind8 = "technology";
export type Origin4 = "source" | "user";
export type Revision23 = number;
export type Subprojectid = string | null;
export type Evidence9 = EvidenceSpan[];
export type Id27 = string;
export type Kind9 = "education";
export type Origin5 = "source" | "user";
export type Revision24 = number;
export type Evidence10 = EvidenceSpan[];
export type Id28 = string;
export type Kind10 = "language";
export type Origin6 = "source" | "user";
export type Revision25 = number;
export type Evidence11 = EvidenceSpan[];
export type Id29 = string;
export type Kind11 = "certification";
export type Origin7 = "source" | "user";
export type Revision26 = number;
export type Evidence12 = EvidenceSpan[];
export type Id30 = string;
export type Jobid2 = string | null;
export type Kind12 = "claim";
export type Origin8 = "source" | "user";
export type Revision27 = number;
export type Subprojectid1 = string | null;
export type Evidence13 = EvidenceSpan[];
export type Id31 = string;
export type Jobid3 = string | null;
export type Kind13 = "metric";
export type Origin9 = "source" | "user";
export type Revision28 = number;
export type Subprojectid2 = string | null;
export type Pendingrawtext3 = string | null;
export type Rawtext4 = string;
export type Revision29 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
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
export type Evidence14 = EvidenceSpan[];
export type Id32 = string;
export type Jobid4 = string | null;
export type Kind14 = "leadership";
export type Origin10 = "source" | "user";
export type Revision30 = number;
export type Subprojectid3 = string | null;
export type Pendingrawtext4 = string | null;
export type Rawtext5 = string;
export type Revision31 = number;
export type Status4 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Category = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence15 = EvidenceSpan[];
export type Id33 = string;
export type Kind15 = "unresolved";
export type Origin11 = "source" | "user";
export type Revision32 = number;
export type Status5 = "unresolved" | "pending" | "conflict";
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
export type Revision33 = number;
export type Actionid = string;
export type Orderindex = number;
export type Recordid5 = string;
export type Revision34 = number;
export type Tombstones = RecordTombstone[];
export type Actionid1 = string | null;
export type Fingerprint = string | null;
export type Id34 = string;
export type Kind16 =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision35 = number;
export type Dependencies = DependencyStamp[];
export type Errorcode = string | null;
export type Id35 = string;
export type Kind17 =
  "extract" | "normalize_semantics" | "draft_prose" | "render" | "project_save" | "rewrite_prose" | "reconcile_edits";
export type Status6 = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type Operations = RichOperation[];
export type Projectid = string;
export type Documentrevision = number;
export type Docxpath = string;
export type Docxsha256 = string;
export type Docxsize = number;
export type Factsrevision = number;
export type Id36 = string;
export type Renderersha256 = string;
export type Rendererversion = string;
export type Templatesha256 = string;
export type Renders = RichRenderSnapshot[];
export type Revision36 = number;
export type Schemaversion1 = 5;
export type Byteref = string;
export type Bytesha256 = string;
export type Id37 = string;
export type Mimetype1 = string;
export type Originalname = string;
export type Id38 = string;
export type Origin12 = "user";
export type Revision37 = number;
export type Text3 = string;
export type Unitid1 = string;
export type Overlays = SourceOverlay[];
export type Parser = string;
export type Parserversion = string;
export type Revision38 = number;
export type Disposition = "shown" | "condensed" | "archived" | "duplicate" | "unresolved" | "administrative";
export type Id39 = string;
export type Column = number | null;
export type Index = number;
export type Kind18 = "page" | "paragraph" | "table_cell" | "pasted";
export type Row = number | null;
export type Order = number;
export type Representedfactids = string[];
export type Revision39 = number;
export type Text4 = string;
export type Units = SourceUnit[];
export type Warnings = string[];
export type Sources = Source[];
export type Path1 = string;
export type Sha2561 = string;
export type Size1 = number;
export type Assets1 = AssetRef[];
export type Contentpolicyversion = string;
export type Id40 = string;
export type Packagesha256 = string;
export type Version = string;

export interface ProjectV5 {
  assets: Assets;
  createdAt: Createdat;
  document: RichDocumentV1;
  evidenceRecords: Evidencerecords;
  facts: WorkingFacts;
  operations: Operations;
  projectId: Projectid;
  renders: Renders;
  revision: Revision36;
  schemaVersion: Schemaversion1;
  sources: Sources;
  template: TemplateManifest;
}
export interface LocalImageAsset {
  height: Height;
  id: Id;
  mimeType: Mimetype;
  path: Path;
  sha256: Sha256;
  size: Size;
  width: Width;
}
export interface RichDocumentV1 {
  regions: Regions;
  revision: Revision14;
  schemaVersion: Schemaversion;
}
export interface RichRegion {
  blocks: Blocks;
  id: Id19;
  revision: Revision13;
  role: Role;
}
export interface ParagraphBlock {
  children: Children;
  content: Content12;
  id: Id18;
  props: ParagraphProps;
  provenance: Provenance11;
  revision: Revision12;
  type: Type14;
}
export interface HeadingBlock {
  children: Children1;
  content: Content11;
  id: Id17;
  props: HeadingProps;
  provenance: Provenance10;
  revision: Revision11;
  type: Type13;
}
export interface BulletBlock {
  children: Children2;
  content: Content10;
  id: Id16;
  props: ParagraphProps;
  provenance: Provenance9;
  revision: Revision10;
  type: Type12;
}
export interface NumberedBlock {
  children: Children3;
  content: Content9;
  id: Id15;
  props: NumberedProps;
  provenance: Provenance8;
  revision: Revision9;
  type: Type11;
}
export interface ChecklistBlock {
  children: Children4;
  content: Content8;
  id: Id14;
  props: ChecklistProps;
  provenance: Provenance7;
  revision: Revision8;
  type: Type10;
}
export interface ToggleBlock {
  children: Children5;
  content: Content7;
  id: Id13;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision7;
  type: Type9;
}
export interface QuoteBlock {
  children: Children6;
  content: Content6;
  id: Id12;
  props: ParagraphProps;
  provenance: Provenance5;
  revision: Revision6;
  type: Type8;
}
export interface CodeBlock {
  children: Children7;
  content: Content5;
  id: Id11;
  props: CodeProps;
  provenance: Provenance4;
  revision: Revision5;
  type: Type7;
}
export interface DividerBlock {
  children: Children8;
  content: Content4;
  id: Id10;
  props: EmptyProps;
  provenance: Provenance3;
  revision: Revision4;
  type: Type6;
}
export interface TableBlock {
  children: Children9;
  content: TableContent;
  id: Id9;
  props: ParagraphProps;
  provenance: Provenance2;
  revision: Revision3;
  type: Type5;
}
export interface ImageBlock {
  children: Children10;
  content: Content2;
  id: Id6;
  props: ImageProps;
  provenance: Provenance1;
  revision: Revision1;
  type: Type4;
}
export interface SectionBlock {
  children: Children11;
  content: Content;
  id: Id1;
  props: SectionProps;
  provenance: Provenance;
  revision: Revision;
  type: Type3;
}
export interface StyledText {
  styles: InlineStyles;
  text: Text;
  type: Type;
}
export interface InlineStyles {
  backgroundColor?: Backgroundcolor;
  bold?: Bold;
  code?: Code;
  italic?: Italic;
  strike?: Strike;
  textColor?: Textcolor;
  underline?: Underline;
}
export interface Hyperlink {
  content: Content1;
  href: Href;
  type: Type1;
}
export interface FactFieldSpan {
  bindingId: Bindingid;
  fieldKey: Fieldkey;
  recordId: Recordid;
  styles: InlineStyles;
  syncedFactRevision: Syncedfactrevision;
  text: Text1;
  type: Type2;
}
export interface SectionProps {
  alignment?: Alignment;
  backgroundColor?: Backgroundcolor1;
  presentation?: Presentation;
  recordId: Recordid1;
  textColor?: Textcolor1;
}
export interface NarrativeCitation {
  evidence: Evidence;
  fieldKeys: Fieldkeys;
  id: Id2;
  kind: Kind;
  recordId: Recordid2;
}
export interface EvidenceSpan {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  text: Text2;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface FieldBinding {
  fieldKey: Fieldkey1;
  id: Id3;
  kind: Kind1;
  recordId: Recordid3;
}
export interface WorkingOwnership {
  id: Id4;
  kind: Kind2;
  recordId: Recordid4;
}
export interface SourceWitness {
  evidence: Evidence1;
  id: Id5;
  kind: Kind3;
}
export interface ImageProps {
  alignment: Alignment1;
  alt: Alt;
  assetId: Assetid;
  caption: Caption;
  height: Height1;
  width: Width1;
}
export interface TableContent {
  columnWidths: Columnwidths;
  headerRows: Headerrows;
  rows: Rows;
}
export interface TableRow {
  cells: Cells;
  id: Id8;
}
export interface TableCell {
  alignment?: Alignment2;
  backgroundColor?: Backgroundcolor2;
  colspan?: Colspan;
  content: Content3;
  id: Id7;
  revision: Revision2;
  rowspan?: Rowspan;
}
export interface ParagraphProps {
  alignment?: Alignment3;
  backgroundColor?: Backgroundcolor3;
  textColor?: Textcolor2;
}
export interface EmptyProps {}
export interface CodeProps {
  backgroundColor?: Backgroundcolor4;
  language: Language;
}
export interface ChecklistProps {
  alignment?: Alignment4;
  backgroundColor?: Backgroundcolor5;
  checked: Checked;
  textColor?: Textcolor3;
}
export interface NumberedProps {
  alignment?: Alignment5;
  backgroundColor?: Backgroundcolor6;
  start?: Start;
  textColor?: Textcolor4;
}
export interface HeadingProps {
  alignment?: Alignment6;
  backgroundColor?: Backgroundcolor7;
  level: Level;
  textColor?: Textcolor5;
}
export interface ImmutableFactEvidence {
  evidence: Evidence2;
  id: Id20;
  rawText: Rawtext;
}
export interface WorkingFacts {
  records: Records;
  revision: Revision33;
  tombstones: Tombstones;
}
export interface CandidateRecord {
  evidence: Evidence3;
  id: Id21;
  kind: Kind4;
  location: WorkingFieldStr;
  name: WorkingFieldStr;
  origin: Origin;
  revision: Revision16;
  title: WorkingFieldStr;
}
export interface WorkingFieldStr {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext1;
  revision: Revision15;
  status: Status;
  value: Value;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence4;
  id: Id22;
  kind: Kind5;
  label: Label;
  origin: Origin1;
  revision: Revision17;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence5;
  id: Id23;
  kind: Kind6;
  origin: Origin2;
  periods: Periods;
  revision: Revision21;
  role: WorkingFieldStr;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence6;
  id: Id24;
  present: WorkingFieldBool;
  revision: Revision20;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext2;
  revision: Revision18;
  status: Status1;
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
  rawText: Rawtext3;
  revision: Revision19;
  status: Status2;
  value: Value1;
}
export interface SubprojectRecord {
  evidence: Evidence7;
  id: Id25;
  jobId: Jobid;
  kind: Kind7;
  name: WorkingFieldStr;
  origin: Origin3;
  periods: Periods1;
  revision: Revision22;
  role: WorkingFieldStr;
}
export interface TechnologyRecord {
  canonicalId: WorkingFieldStr;
  display: WorkingFieldStr;
  evidence: Evidence8;
  id: Id26;
  jobId: Jobid1;
  kind: Kind8;
  origin: Origin4;
  revision: Revision23;
  subprojectId: Subprojectid;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence9;
  id: Id27;
  institution: WorkingFieldStr;
  kind: Kind9;
  origin: Origin5;
  qualification: WorkingFieldStr;
  revision: Revision24;
  specialty: WorkingFieldStr;
}
export interface LanguageRecord {
  evidence: Evidence10;
  id: Id28;
  kind: Kind10;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin6;
  revision: Revision25;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence11;
  id: Id29;
  issuer: WorkingFieldStr;
  kind: Kind11;
  name: WorkingFieldStr;
  origin: Origin7;
  revision: Revision26;
}
export interface ClaimRecord {
  evidence: Evidence12;
  id: Id30;
  jobId: Jobid2;
  kind: Kind12;
  origin: Origin8;
  revision: Revision27;
  subprojectId: Subprojectid1;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence13;
  id: Id31;
  jobId: Jobid3;
  kind: Kind13;
  origin: Origin9;
  revision: Revision28;
  subprojectId: Subprojectid2;
  value: WorkingFieldMetricValue;
}
export interface WorkingFieldMetricValue {
  pendingRawText: Pendingrawtext3;
  rawText: Rawtext4;
  revision: Revision29;
  status: Status3;
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
  evidence: Evidence14;
  id: Id32;
  jobId: Jobid4;
  kind: Kind14;
  origin: Origin10;
  revision: Revision30;
  subprojectId: Subprojectid3;
  value: WorkingFieldLeadershipValue;
}
export interface WorkingFieldLeadershipValue {
  pendingRawText: Pendingrawtext4;
  rawText: Rawtext5;
  revision: Revision31;
  status: Status4;
  value: LeadershipValue | null;
}
export interface LeadershipValue {
  action: Action;
  attribution: Attribution1;
  teamSize: MetricValue | null;
}
export interface UnresolvedRecord {
  category: Category;
  evidence: Evidence15;
  id: Id33;
  kind: Kind15;
  origin: Origin11;
  revision: Revision32;
  status: Status5;
}
export interface RecordTombstone {
  actionId: Actionid;
  orderIndex: Orderindex;
  recordId: Recordid5;
  revision: Revision34;
}
export interface RichOperation {
  actionId: Actionid1;
  dependencies: Dependencies;
  errorCode: Errorcode;
  id: Id35;
  kind: Kind17;
  status: Status6;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id34;
  kind: Kind16;
  revision: Revision35;
}
export interface RichRenderSnapshot {
  documentRevision: Documentrevision;
  docxPath: Docxpath;
  docxSha256: Docxsha256;
  docxSize: Docxsize;
  factsRevision: Factsrevision;
  id: Id36;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  templateSha256: Templatesha256;
}
export interface Source {
  byteRef: Byteref;
  byteSha256: Bytesha256;
  id: Id37;
  mimeType: Mimetype1;
  originalName: Originalname;
  overlays: Overlays;
  parser: Parser;
  parserVersion: Parserversion;
  revision: Revision38;
  units: Units;
  warnings: Warnings;
}
export interface SourceOverlay {
  id: Id38;
  origin: Origin12;
  revision: Revision37;
  text: Text3;
  unitId: Unitid1;
}
export interface SourceUnit {
  disposition: Disposition;
  id: Id39;
  location: SourceLocation;
  order: Order;
  representedFactIds: Representedfactids;
  revision: Revision39;
  text: Text4;
}
export interface SourceLocation {
  column: Column;
  index: Index;
  kind: Kind18;
  row: Row;
}
export interface TemplateManifest {
  assets: Assets1;
  contentPolicyVersion: Contentpolicyversion;
  id: Id40;
  packageSha256: Packagesha256;
  version: Version;
}
export interface AssetRef {
  path: Path1;
  sha256: Sha2561;
  size: Size1;
}
