export type Blockid = string | null;
export type Cellid = string | null;
export type Fingerprint = string | null;
export type Id = string;
export type Kind =
  "block" | "record" | "field" | "period" | "ownership" | "source" | "rules" | "asset" | "timeline_order";
export type Revision = number;
/**
 * @maxItems 100
 */
export type Dependencies = DependencyStamp[];
export type End = number | null;
export type Fieldkey = string | null;
export type Recordid = string | null;
export type Start = number | null;
export type Text = string;
/**
 * @maxItems 100
 */
export type Affected = AgentAnchor[];
export type Affectedcount = number | null;
export type Kind1 = "entity";
export type Fingerprint1 = string;
export type Kind2 = "query";
export type Cursor = string | null;
/**
 * @maxItems 100
 */
export type Ids = string[];
export type Kind3 = "context" | "document" | "find" | "facts" | "source" | "history" | "resources";
export type Parentid = string | null;
export type Text1 = string;
/**
 * @maxItems 2000
 */
export type Dependencies1 = (AgentEntityDependency | AgentQueryDependency)[];
/**
 * @maxItems 100
 */
export type Factrecordids = string[];
export type Id1 = string;
export type Actionid = string;
export type Actionid1 = string;
export type Actiontoken = number;
export type Dependencies2 = DependencyStamp[];
export type Sessionid = string;
export type Clientmutationid = string;
export type Kind4 =
  "typing" | "composition" | "structure" | "panel" | "rewrite" | "reconciliation" | "cascade" | "undo" | "redo";
export type Projectid = string;
export type Schemaversion = 1;
/**
 * @minItems 1
 * @maxItems 1000
 */
export type Steps = [
  PutBlock | RemoveBlock | MoveBlock | ReplaceInlineRange | PutRecord | RemoveRecord,
  ...(PutBlock | RemoveBlock | MoveBlock | ReplaceInlineRange | PutRecord | RemoveRecord)[]
];
export type Afterid = string | null;
export type Beforerevision = number | null;
export type Block =
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
  | SectionBlock;
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
export type Text2 = string;
export type Type = "text";
export type Content1 = StyledText[];
export type Href = string;
export type Type1 = "link";
export type Bindingid = string;
export type Bindingrootid = string | null;
export type Fieldkey1 = string;
export type Recordid1 = string;
export type Syncedfactrevision = number;
export type Text3 = string;
export type Type2 = "fact_field";
export type Content = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id2 = string;
export type Alignment = "left" | "center" | "right" | "justify";
export type Backgroundcolor1 = string;
export type Manualorder = boolean;
export type Presentation = "standard" | "focus";
export type Recordid2 = string | null;
export type Textcolor1 = string;
export type Sourceid = string;
export type Sourcerevision = number;
export type Text4 = string;
export type Unitid = string;
export type Unitrevision = number;
export type Evidence = EvidenceSpan[];
export type Fieldkeys = string[];
export type Id3 = string;
export type Kind5 = "citation";
export type Recordid3 = string;
export type Fieldkey2 = string;
export type Id4 = string;
export type Kind6 = "field_binding";
export type Recordid4 = string;
export type Id5 = string;
export type Kind7 = "working_owner";
export type Recordid5 = string;
/**
 * @minItems 1
 */
export type Evidence1 = [EvidenceSpan, ...EvidenceSpan[]];
export type Id6 = string;
export type Kind8 = "source";
export type Provenance = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision1 = number;
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
export type Id7 = string;
export type Alignment1 = "left" | "center" | "right";
export type Alt = string;
export type Assetid = string;
export type Caption = (StyledText | Hyperlink | FactFieldSpan)[];
export type Height = number;
export type Width = number;
export type Provenance1 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision2 = number;
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
export type Headercols = number;
export type Headerrows = number;
/**
 * @minItems 1
 */
export type Rows = [TableRow, ...TableRow[]];
export type Alignment2 = "left" | "center" | "right" | "justify";
export type Backgroundcolor2 = string;
export type Colspan = number;
export type Content3 = (StyledText | Hyperlink | FactFieldSpan)[];
export type Id8 = string;
export type Revision3 = number;
export type Rowspan = number;
export type Cells = TableCell[];
export type Id9 = string;
export type Id10 = string;
export type Alignment3 = "left" | "center" | "right" | "justify";
export type Backgroundcolor3 = string;
export type Textcolor2 = string;
export type Provenance2 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision4 = number;
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
export type Id11 = string;
export type Provenance3 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision5 = number;
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
export type Id12 = string;
export type Backgroundcolor4 = string;
export type Language = string;
export type Provenance4 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision6 = number;
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
export type Id13 = string;
export type Provenance5 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision7 = number;
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
export type Id14 = string;
export type Provenance6 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision8 = number;
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
export type Id15 = string;
export type Alignment4 = "left" | "center" | "right" | "justify";
export type Backgroundcolor5 = string;
export type Checked = boolean;
export type Textcolor3 = string;
export type Provenance7 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision9 = number;
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
export type Id16 = string;
export type Alignment5 = "left" | "center" | "right" | "justify";
export type Backgroundcolor6 = string;
export type Start1 = number | null;
export type Textcolor4 = string;
export type Provenance8 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision10 = number;
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
export type Id17 = string;
export type Provenance9 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision11 = number;
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
export type Id18 = string;
export type Alignment6 = "left" | "center" | "right" | "justify";
export type Backgroundcolor7 = string;
export type Level = 1 | 2 | 3;
export type Textcolor5 = string;
export type Provenance10 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision12 = number;
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
export type Id19 = string;
export type Provenance11 = (NarrativeCitation | FieldBinding | WorkingOwnership | SourceWitness)[];
export type Revision13 = number;
export type Type14 = "paragraph";
export type Keepchildren = boolean;
export type Kind9 = "put_block";
export type Parentid1 = string;
export type Beforerevision1 = number;
export type Blockid1 = string;
export type Kind10 = "remove_block";
export type Afterid1 = string | null;
export type Beforerevision2 = number;
export type Blockid2 = string;
export type Kind11 = "move_block";
export type Parentid2 = string;
export type Beforerevision3 = number;
export type Blockid3 = string;
export type Cellid1 = string | null;
export type Content13 = (StyledText | Hyperlink | FactFieldSpan)[];
/**
 * UTF-16 code units within the selected inline field.
 */
export type End1 = number;
export type Field = "content" | "caption";
export type Kind12 = "replace_inline_range";
/**
 * UTF-16 code units within the selected inline field.
 */
export type Start2 = number;
export type Beforerevision4 = number | null;
export type Kind13 = "put_record";
export type Record =
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
  | UnresolvedRecord;
export type Evidence2 = EvidenceSpan[];
export type Id20 = string;
export type Kind14 = "candidate";
export type Pendingrawtext = string | null;
export type Rawtext = string;
export type Revision14 = number;
export type Status = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected = boolean;
export type Value = string | null;
export type Origin = "source" | "user";
export type Revision15 = number;
export type Usercorrected1 = boolean;
export type Detailtype = "phone" | "email" | "url" | "messenger" | "age" | "birth_date" | "metadata" | "other";
export type Evidence3 = EvidenceSpan[];
export type Id21 = string;
export type Kind15 = "detail";
export type Label = string;
export type Origin1 = "source" | "user";
export type Revision16 = number;
export type Usercorrected2 = boolean;
export type Evidence4 = EvidenceSpan[];
export type Id22 = string;
export type Kind16 = "employment";
export type Origin2 = "source" | "user";
export type Pendingrawtext1 = string | null;
export type Rawtext1 = string;
export type Revision17 = number;
export type Status1 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected3 = boolean;
export type Day = number | null;
export type Month = number | null;
export type Precision = "year" | "month" | "day";
export type Year = number;
export type Evidence5 = EvidenceSpan[];
export type Id23 = string;
export type Pendingrawtext2 = string | null;
export type Rawtext2 = string;
export type Revision18 = number;
export type Status2 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected4 = boolean;
export type Value1 = boolean | null;
export type Revision19 = number;
export type Periods = WorkingPeriod[];
export type Revision20 = number;
export type Usercorrected5 = boolean;
export type Evidence6 = EvidenceSpan[];
export type Id24 = string;
export type Jobid = string;
export type Kind17 = "subproject";
export type Origin3 = "source" | "user";
export type Periods1 = WorkingPeriod[];
export type Revision21 = number;
export type Usercorrected6 = boolean;
export type Evidence7 = EvidenceSpan[];
export type Id25 = string;
export type Jobid1 = string | null;
export type Kind18 = "technology";
export type Origin4 = "source" | "user";
export type Revision22 = number;
export type Subprojectid = string | null;
export type Technical = boolean | null;
export type Usercorrected7 = boolean;
export type Evidence8 = EvidenceSpan[];
export type Id26 = string;
export type Kind19 = "education";
export type Origin5 = "source" | "user";
export type Revision23 = number;
export type Usercorrected8 = boolean;
export type Evidence9 = EvidenceSpan[];
export type Id27 = string;
export type Kind20 = "language";
export type Origin6 = "source" | "user";
export type Revision24 = number;
export type Usercorrected9 = boolean;
export type Evidence10 = EvidenceSpan[];
export type Id28 = string;
export type Kind21 = "certification";
export type Origin7 = "source" | "user";
export type Revision25 = number;
export type Usercorrected10 = boolean;
export type Evidence11 = EvidenceSpan[];
export type Id29 = string;
export type Jobid2 = string | null;
export type Kind22 = "claim";
export type Origin8 = "source" | "user";
export type Revision26 = number;
export type Subprojectid1 = string | null;
export type Usercorrected11 = boolean;
export type Evidence12 = EvidenceSpan[];
export type Id30 = string;
export type Jobid3 = string | null;
export type Kind23 = "metric";
export type Origin9 = "source" | "user";
export type Revision27 = number;
export type Subprojectid2 = string | null;
export type Usercorrected12 = boolean;
export type Pendingrawtext3 = string | null;
export type Rawtext3 = string;
export type Revision28 = number;
export type Status3 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected13 = boolean;
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
export type Id31 = string;
export type Jobid4 = string | null;
export type Kind24 = "leadership";
export type Origin10 = "source" | "user";
export type Revision29 = number;
export type Subprojectid3 = string | null;
export type Usercorrected14 = boolean;
export type Pendingrawtext4 = string | null;
export type Rawtext4 = string;
export type Revision30 = number;
export type Status4 = "known" | "unknown" | "unresolved" | "pending" | "conflict";
export type Usercorrected15 = boolean;
export type Action = string;
export type Attribution1 = "personal" | "team" | "organization" | "unknown";
export type Category = "education" | "certification" | "language" | "employment" | "detail" | "other";
export type Evidence14 = EvidenceSpan[];
export type Id32 = string;
export type Kind25 = "unresolved";
export type Origin11 = "source" | "user";
export type Revision31 = number;
export type Status5 = "unresolved" | "pending" | "conflict";
export type Usercorrected16 = boolean;
export type Beforerevision5 = number;
export type Kind26 = "remove_record";
export type Recordid6 = string;
export type Ownerepoch = number;
export type Previewsha256 = string;
/**
 * @maxItems 64
 */
export type Readsnapshotids = string[];
export type Requestsha256 = string;
export type Runid = string;
export type Scope1 = WholeResumeScope | SelectionScope;
export type Kind27 = "resume";
export type Kind28 = "selection";
export type Blockid4 = string;
export type Cellid2 = string | null;
/**
 * UTF-16 code units within the block or cell.
 */
export type Offset = number;
/**
 * @minItems 1
 */
export type Blockids = [string, ...string[]];
export type Kind29 = "text" | "blocks" | "table_cells";
export type Textsha256 = string;
export type State =
  | "prepared"
  | "offered"
  | "applying"
  | "saved"
  | "stale"
  | "rejected"
  | "cancelled"
  | "save_failed"
  | "outcome_unknown";
export type Toolkey = string;

export interface AgentEditBatch {
  affected: Affected;
  affectedCount?: Affectedcount;
  dependencies: Dependencies1;
  factRecordIds: Factrecordids;
  id: Id1;
  mutation: RichMutation;
  ownerEpoch: Ownerepoch;
  previewSha256: Previewsha256;
  readSnapshotIds: Readsnapshotids;
  requestSha256: Requestsha256;
  runId: Runid;
  scope: Scope1;
  state: State;
  toolKey: Toolkey;
}
export interface AgentAnchor {
  blockId: Blockid;
  cellId: Cellid;
  dependencies: Dependencies;
  end: End;
  fieldKey: Fieldkey;
  recordId: Recordid;
  start: Start;
  text: Text;
}
export interface DependencyStamp {
  fingerprint: Fingerprint;
  id: Id;
  kind: Kind;
  revision: Revision;
}
export interface AgentEntityDependency {
  kind: Kind1;
  stamp: DependencyStamp;
}
export interface AgentQueryDependency {
  fingerprint: Fingerprint1;
  kind: Kind2;
  query: AgentQuery;
}
export interface AgentQuery {
  cursor?: Cursor;
  ids?: Ids;
  kind: Kind3;
  parentId?: Parentid;
  text?: Text1;
}
export interface RichMutation {
  actionId: Actionid;
  capture: ActionCapture;
  clientMutationId: Clientmutationid;
  kind: Kind4;
  projectId: Projectid;
  schemaVersion: Schemaversion;
  steps: Steps;
}
export interface ActionCapture {
  actionId: Actionid1;
  actionToken: Actiontoken;
  dependencies: Dependencies2;
  sessionId: Sessionid;
}
export interface PutBlock {
  afterId: Afterid;
  beforeRevision: Beforerevision;
  block: Block;
  keepChildren?: Keepchildren;
  kind: Kind9;
  parentId: Parentid1;
}
export interface ParagraphBlock {
  children: Children;
  content: Content12;
  id: Id19;
  props: ParagraphProps;
  provenance: Provenance11;
  revision: Revision13;
  type: Type14;
}
export interface HeadingBlock {
  children: Children1;
  content: Content11;
  id: Id18;
  props: HeadingProps;
  provenance: Provenance10;
  revision: Revision12;
  type: Type13;
}
export interface BulletBlock {
  children: Children2;
  content: Content10;
  id: Id17;
  props: ParagraphProps;
  provenance: Provenance9;
  revision: Revision11;
  type: Type12;
}
export interface NumberedBlock {
  children: Children3;
  content: Content9;
  id: Id16;
  props: NumberedProps;
  provenance: Provenance8;
  revision: Revision10;
  type: Type11;
}
export interface ChecklistBlock {
  children: Children4;
  content: Content8;
  id: Id15;
  props: ChecklistProps;
  provenance: Provenance7;
  revision: Revision9;
  type: Type10;
}
export interface ToggleBlock {
  children: Children5;
  content: Content7;
  id: Id14;
  props: ParagraphProps;
  provenance: Provenance6;
  revision: Revision8;
  type: Type9;
}
export interface QuoteBlock {
  children: Children6;
  content: Content6;
  id: Id13;
  props: ParagraphProps;
  provenance: Provenance5;
  revision: Revision7;
  type: Type8;
}
export interface CodeBlock {
  children: Children7;
  content: Content5;
  id: Id12;
  props: CodeProps;
  provenance: Provenance4;
  revision: Revision6;
  type: Type7;
}
export interface DividerBlock {
  children: Children8;
  content: Content4;
  id: Id11;
  props: EmptyProps;
  provenance: Provenance3;
  revision: Revision5;
  type: Type6;
}
export interface TableBlock {
  children: Children9;
  content: TableContent;
  id: Id10;
  props: ParagraphProps;
  provenance: Provenance2;
  revision: Revision4;
  type: Type5;
}
export interface ImageBlock {
  children: Children10;
  content: Content2;
  id: Id7;
  props: ImageProps;
  provenance: Provenance1;
  revision: Revision2;
  type: Type4;
}
export interface SectionBlock {
  children: Children11;
  content: Content;
  id: Id2;
  props: SectionProps;
  provenance: Provenance;
  revision: Revision1;
  type: Type3;
}
export interface StyledText {
  styles: InlineStyles;
  text: Text2;
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
  bindingRootId?: Bindingrootid;
  fieldKey: Fieldkey1;
  recordId: Recordid1;
  styles: InlineStyles;
  syncedFactRevision: Syncedfactrevision;
  text: Text3;
  type: Type2;
}
export interface SectionProps {
  alignment?: Alignment;
  backgroundColor?: Backgroundcolor1;
  manualOrder?: Manualorder;
  presentation?: Presentation;
  recordId: Recordid2;
  textColor?: Textcolor1;
}
export interface NarrativeCitation {
  evidence: Evidence;
  fieldKeys: Fieldkeys;
  id: Id3;
  kind: Kind5;
  recordId: Recordid3;
}
export interface EvidenceSpan {
  sourceId: Sourceid;
  sourceRevision: Sourcerevision;
  text: Text4;
  unitId: Unitid;
  unitRevision: Unitrevision;
}
export interface FieldBinding {
  fieldKey: Fieldkey2;
  id: Id4;
  kind: Kind6;
  recordId: Recordid4;
}
export interface WorkingOwnership {
  id: Id5;
  kind: Kind7;
  recordId: Recordid5;
}
export interface SourceWitness {
  evidence: Evidence1;
  id: Id6;
  kind: Kind8;
}
export interface ImageProps {
  alignment: Alignment1;
  alt: Alt;
  assetId: Assetid;
  caption: Caption;
  height: Height;
  width: Width;
}
export interface TableContent {
  columnWidths: Columnwidths;
  headerCols?: Headercols;
  headerRows: Headerrows;
  rows: Rows;
}
export interface TableRow {
  cells: Cells;
  id: Id9;
}
export interface TableCell {
  alignment?: Alignment2;
  backgroundColor?: Backgroundcolor2;
  colspan?: Colspan;
  content: Content3;
  id: Id8;
  revision: Revision3;
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
  start?: Start1;
  textColor?: Textcolor4;
}
export interface HeadingProps {
  alignment?: Alignment6;
  backgroundColor?: Backgroundcolor7;
  level: Level;
  textColor?: Textcolor5;
}
export interface RemoveBlock {
  beforeRevision: Beforerevision1;
  blockId: Blockid1;
  kind: Kind10;
}
export interface MoveBlock {
  afterId: Afterid1;
  beforeRevision: Beforerevision2;
  blockId: Blockid2;
  kind: Kind11;
  parentId: Parentid2;
}
export interface ReplaceInlineRange {
  beforeRevision: Beforerevision3;
  blockId: Blockid3;
  cellId: Cellid1;
  content: Content13;
  end: End1;
  field: Field;
  kind: Kind12;
  start: Start2;
}
export interface PutRecord {
  beforeRevision: Beforerevision4;
  kind: Kind13;
  record: Record;
}
export interface CandidateRecord {
  evidence: Evidence2;
  id: Id20;
  kind: Kind14;
  location: WorkingFieldStr;
  name: WorkingFieldStr;
  origin: Origin;
  revision: Revision15;
  title: WorkingFieldStr;
  userCorrected?: Usercorrected1;
}
export interface WorkingFieldStr {
  pendingRawText: Pendingrawtext;
  rawText: Rawtext;
  revision: Revision14;
  status: Status;
  userCorrected?: Usercorrected;
  value: Value;
}
export interface DetailRecord {
  detailType: Detailtype;
  evidence: Evidence3;
  id: Id21;
  kind: Kind15;
  label: Label;
  origin: Origin1;
  revision: Revision16;
  userCorrected?: Usercorrected2;
  value: WorkingFieldStr;
}
export interface EmploymentRecord {
  employer: WorkingFieldStr;
  evidence: Evidence4;
  id: Id22;
  kind: Kind16;
  origin: Origin2;
  periods: Periods;
  revision: Revision20;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected5;
}
export interface WorkingPeriod {
  end: WorkingFieldPartialDate;
  evidence: Evidence5;
  id: Id23;
  present: WorkingFieldBool;
  revision: Revision19;
  start: WorkingFieldPartialDate;
}
export interface WorkingFieldPartialDate {
  pendingRawText: Pendingrawtext1;
  rawText: Rawtext1;
  revision: Revision17;
  status: Status1;
  userCorrected?: Usercorrected3;
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
  revision: Revision18;
  status: Status2;
  userCorrected?: Usercorrected4;
  value: Value1;
}
export interface SubprojectRecord {
  evidence: Evidence6;
  id: Id24;
  jobId: Jobid;
  kind: Kind17;
  name: WorkingFieldStr;
  origin: Origin3;
  periods: Periods1;
  revision: Revision21;
  role: WorkingFieldStr;
  userCorrected?: Usercorrected6;
}
export interface TechnologyRecord {
  canonicalId: WorkingFieldStr;
  display: WorkingFieldStr;
  evidence: Evidence7;
  experience?: WorkingFieldStr;
  id: Id25;
  jobId: Jobid1;
  kind: Kind18;
  origin: Origin4;
  revision: Revision22;
  subprojectId: Subprojectid;
  technical?: Technical;
  userCorrected?: Usercorrected7;
}
export interface EducationRecord {
  completion: WorkingFieldPartialDate;
  evidence: Evidence8;
  id: Id26;
  institution: WorkingFieldStr;
  kind: Kind19;
  origin: Origin5;
  qualification: WorkingFieldStr;
  revision: Revision23;
  specialty: WorkingFieldStr;
  userCorrected?: Usercorrected8;
}
export interface LanguageRecord {
  evidence: Evidence9;
  id: Id27;
  kind: Kind20;
  language: WorkingFieldStr;
  level: WorkingFieldStr;
  origin: Origin6;
  revision: Revision24;
  userCorrected?: Usercorrected9;
}
export interface CertificationRecord {
  date: WorkingFieldPartialDate;
  evidence: Evidence10;
  id: Id28;
  issuer: WorkingFieldStr;
  kind: Kind21;
  name: WorkingFieldStr;
  origin: Origin7;
  revision: Revision25;
  userCorrected?: Usercorrected10;
}
export interface ClaimRecord {
  evidence: Evidence11;
  id: Id29;
  jobId: Jobid2;
  kind: Kind22;
  origin: Origin8;
  revision: Revision26;
  subprojectId: Subprojectid1;
  userCorrected?: Usercorrected11;
  value: WorkingFieldStr;
}
export interface MetricRecord {
  evidence: Evidence12;
  id: Id30;
  jobId: Jobid3;
  kind: Kind23;
  origin: Origin9;
  revision: Revision27;
  subprojectId: Subprojectid2;
  userCorrected?: Usercorrected12;
  value: WorkingFieldMetricValue;
}
export interface WorkingFieldMetricValue {
  pendingRawText: Pendingrawtext3;
  rawText: Rawtext3;
  revision: Revision28;
  status: Status3;
  userCorrected?: Usercorrected13;
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
  id: Id31;
  jobId: Jobid4;
  kind: Kind24;
  origin: Origin10;
  revision: Revision29;
  subprojectId: Subprojectid3;
  userCorrected?: Usercorrected14;
  value: WorkingFieldLeadershipValue;
}
export interface WorkingFieldLeadershipValue {
  pendingRawText: Pendingrawtext4;
  rawText: Rawtext4;
  revision: Revision30;
  status: Status4;
  userCorrected?: Usercorrected15;
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
  id: Id32;
  kind: Kind25;
  origin: Origin11;
  revision: Revision31;
  status: Status5;
  userCorrected?: Usercorrected16;
}
export interface RemoveRecord {
  beforeRevision: Beforerevision5;
  kind: Kind26;
  recordId: Recordid6;
}
export interface WholeResumeScope {
  kind: Kind27;
}
export interface SelectionScope {
  kind: Kind28;
  selection: RichSelection;
}
export interface RichSelection {
  anchor: RichPosition;
  blockIds: Blockids;
  capture: ActionCapture;
  head: RichPosition;
  kind: Kind29;
  textSha256: Textsha256;
}
export interface RichPosition {
  blockId: Blockid4;
  cellId: Cellid2;
  offset: Offset;
}
